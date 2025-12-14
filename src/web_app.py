# -*- coding: utf-8 -*-
from __future__ import annotations

import glob
import json
import os
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime, date

import pandas as pd
from flask import Flask, render_template, jsonify, request, Response
from time import time as _time

from src.performance import calculate_performance
from src.data_fetcher import fetch_etf_data, save_to_db

# load .env so INITIAL_CAPITAL or other settings take effect in web
from dotenv import load_dotenv
load_dotenv(override=True)

# Optional: akshare for live quotes
try:
    import akshare as ak
except Exception:
    ak = None

# Track last live source used
_LAST_TICKER_SOURCE = "unknown"

# ---- Configure akshare session (headers + retry) ----
def _configure_ak_session():
    global ak
    if ak is None:
        return
    try:
        import requests
        from requests.adapters import HTTPAdapter
        try:
            from urllib3.util.retry import Retry
        except Exception:
            # Fallback name in newer urllib3
            from urllib3.util import Retry  # type: ignore
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://quote.eastmoney.com/",
            "Connection": "keep-alive",
        }
        try:
            ak.headers = headers  # type: ignore[attr-defined]
        except Exception:
            pass
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        try:
            ak.session = s  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception:
        pass

_configure_ak_session()

# ---- Optional Qlib initialization ----
QLIB_ENABLED = os.getenv("QLIB_ENABLE", "false").lower() == "true"
QLIB_REGION = os.getenv("QLIB_REGION", "cn")
QLIB_DIR = os.getenv(
    "QLIB_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "qlib", "cn_etf")),
)
QLIB_INITED = False
QLIB_ERROR = None

def _qlib_installed() -> bool:
    try:
        import qlib  # type: ignore
        return True
    except Exception:
        return False

if QLIB_ENABLED:
    try:
        import qlib  # type: ignore
        qlib.init(provider_uri=os.path.abspath(QLIB_DIR), region=QLIB_REGION)
        QLIB_INITED = True
    except Exception as e:
        QLIB_ERROR = str(e)

# --- helpers for reading latest prices from etf db ---
import sqlite3 as _sqlite3


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _db_path() -> str:
    return os.path.join(_project_root(), "data", "trade_history.db")


def _etf_db_path() -> str:
    return os.path.join(_project_root(), "data", "etf_data.db")


def _read_latest_price(code: str) -> float | None:
    db = _etf_db_path()
    if not os.path.exists(db):
        return None
    conn = _sqlite3.connect(db)
    try:
        try:
            df = pd.read_sql_query(f"SELECT * FROM etf_{code} ORDER BY 日期 DESC LIMIT 1", conn)
        except Exception:
            df = pd.read_sql_query(f"SELECT * FROM etf_{code} ORDER BY date DESC LIMIT 1", conn)
        if df.empty:
            return None
        for col in ("收盘", "收盘价", "close", "Close"):
            if col in df.columns:
                try:
                    return float(df.iloc[0][col])
                except Exception:
                    continue
        return None
    except Exception:
        return None
    finally:
        conn.close()


app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "..", "static"),
    template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
)
# Front-end refresh friendliness
app.config["TEMPLATES_AUTO_RELOAD"] = True
try:
    if os.getenv("FLASK_DEBUG", "false").lower() == "true":
        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
except Exception:
    pass


@app.after_request
def add_no_cache_headers(resp):
    try:
        ct = resp.headers.get("Content-Type", "")
        # Disable caching for HTML and JSON responses
        if ("text/html" in ct) or ("application/json" in ct):
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
    except Exception:
        pass
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return "ok", 200


@app.route("/api/refresh_prices", methods=["POST"])
def refresh_prices():
    """手动拉取AKShare行情并更新数据库。"""
    etf_list_env = os.getenv("ETF_LIST", "")
    etf_codes = [code.strip() for code in etf_list_env.split(",") if code.strip()]
    if not etf_codes:
        return jsonify({"ok": False, "msg": "ETF_LIST 为空"}), 400
    if ak is None:
        return jsonify({"ok": False, "msg": "akshare 未安装"}), 400
    updated = 0
    errors: list[dict] = []
    for code in etf_codes:
        try:
            df = fetch_etf_data(code, days=int(os.getenv("REFRESH_DAYS", "700")))
            save_to_db(df, code, db_path=_etf_db_path())
            updated += 1
        except Exception as e:
            errors.append({"code": code, "error": str(e)})
    return jsonify({"ok": True, "updated": updated, "errors": errors})


@app.route("/api/etf_tickers")
def get_etf_tickers():
    """获取ETF_LIST中所有ETF的最新行情快照。"""
    etf_list_env = os.getenv("ETF_LIST", "")
    etf_codes = [code.strip() for code in etf_list_env.split(",") if code.strip()]

    def _market_open_local() -> bool:
        import datetime as _dt
        now = _dt.datetime.now()
        wd = now.weekday()
        if wd >= 5:
            return False
        hm = now.hour * 60 + now.minute
        return (570 <= hm <= 690) or (780 <= hm <= 900)

    want_live = (request.args.get("live", "0") == "1")
    if want_live and ak is not None:
        is_open = _market_open_local()
        rows: list[dict] = []
        src = "unknown"
        global _LAST_TICKER_SOURCE
        try:
            # Primary source: Eastmoney
            spot = None
            try:
                spot = ak.fund_etf_spot_em()
                src = "eastmoney"
            except Exception:
                spot = None
            # Fallback 1: THS (同花顺)
            if (spot is None) or (not isinstance(spot, pd.DataFrame)) or spot.empty:
                try:
                    spot = ak.fund_etf_spot_ths()
                    src = "ths"
                except Exception:
                    spot = None

            if isinstance(spot, pd.DataFrame) and not spot.empty:
                def pick(df: pd.DataFrame, *cands):
                    for c in cands:
                        if c in df.columns:
                            return c
                    return None
                code_c = pick(spot, "代码", "symbol", "代码code", "code")
                name_c = pick(spot, "名称", "name")
                price_c = pick(spot, "最新价", "最新价(元)", "现价", "最新", "price")
                chg_c = pick(spot, "涨跌额", "change")
                pct_c = pick(spot, "涨跌幅", "涨跌幅(%)", "pct_change")
                vol_c = pick(spot, "成交量", "volume", "成交量(手)")
                if code_c and price_c:
                    sub = spot.loc[spot[code_c].astype(str).isin(etf_codes)].copy()
                    for _, r in sub.iterrows():
                        try:
                            code = str(r.get(code_c))
                            name = (str(r.get(name_c)) if name_c else "-")
                            price = float(r.get(price_c)) if pd.notna(r.get(price_c)) else None
                            change = float(r.get(chg_c)) if (chg_c and pd.notna(r.get(chg_c))) else 0.0
                            pct = float(r.get(pct_c)) if (pct_c and pd.notna(r.get(pct_c))) else 0.0
                            vol = float(r.get(vol_c)) if (vol_c and pd.notna(r.get(vol_c))) else 0.0
                            rows.append({
                                "code": code,
                                "name": name,
                                "date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "price": price,
                                "change": change,
                                "pct_change": pct,
                                "volume": vol,
                            })
                        except Exception:
                            continue
        except Exception:
            rows = []
        if not rows:
            _LAST_TICKER_SOURCE = "history"
            return jsonify({"market_open": is_open, "source": _LAST_TICKER_SOURCE, "rows": _read_hist_tickers_safe(etf_codes)})
        _LAST_TICKER_SOURCE = src
        return jsonify({"market_open": is_open, "source": _LAST_TICKER_SOURCE, "rows": rows})

    return jsonify(_read_hist_tickers_safe(etf_codes))


def _read_hist_tickers(etf_codes: list[str]) -> list[dict]:
    tickers: list[dict] = []
    etf_db = _etf_db_path()
    if not os.path.exists(etf_db):
        return tickers

    # 名称映射（可选）
    name_map: dict[str, str] = {}
    if ak is not None:
        try:
            spot = ak.fund_etf_spot_em()
            if isinstance(spot, pd.DataFrame) and not spot.empty:
                code_c = next((c for c in ("代码", "symbol", "代码code") if c in spot.columns), None)
                name_c = next((c for c in ("名称", "name") if c in spot.columns), None)
                if code_c and name_c:
                    for _, r in spot.iterrows():
                        try:
                            name_map[str(r.get(code_c))] = str(r.get(name_c))
                        except Exception:
                            continue
        except Exception:
            pass

    conn = _sqlite3.connect(etf_db)
    try:
        for code in etf_codes:
            try:
                try:
                    df = pd.read_sql_query(f"SELECT * FROM etf_{code} ORDER BY 日期 DESC LIMIT 2", conn)
                except Exception:
                    df = pd.read_sql_query(f"SELECT * FROM etf_{code} ORDER BY date DESC LIMIT 2", conn)
                if df.empty:
                    continue

                def pick(cols: list[str]):
                    for c in cols:
                        if c in df.columns:
                            return c
                    return None

                date_col = pick(["日期", "date", "Date"])
                close_col = pick(["收盘", "收盘价", "close", "Close"])  # 价格列
                vol_col = pick(["成交量", "volume", "Volume", "成交量(手)"])  # 成交量
                name_col = pick(["名称", "name", "Name"])  # 名称（可选）
                if not date_col or not close_col:
                    continue

                latest = df.iloc[0]
                try:
                    prev_close = float(df.iloc[1][close_col]) if len(df) > 1 else float(latest[close_col])
                except Exception:
                    prev_close = None
                try:
                    close = float(latest[close_col])
                except Exception:
                    continue

                if prev_close is None or prev_close == 0 or not (prev_close == prev_close):
                    change = 0.0
                    pct_change = 0.0
                else:
                    change = float(close) - float(prev_close)
                    pct_change = (change / float(prev_close) * 100.0)

                date_val = latest.get(date_col)
                try:
                    date_val = pd.to_datetime(date_val).strftime("%Y-%m-%d")
                except Exception:
                    date_val = str(date_val)

                vol_val = latest.get(vol_col, 0)
                try:
                    vol_val = float(vol_val)
                except Exception:
                    pass

                name_val = latest.get(name_col) if name_col else None
                try:
                    is_nan = pd.isna(name_val)
                except Exception:
                    is_nan = False
                if (not name_val) or is_nan:
                    name_val = name_map.get(code, "-")

                tickers.append({
                    "code": code,
                    "name": str(name_val) if name_val is not None else "-",
                    "date": date_val,
                    "price": float(close),
                    "change": float(change),
                    "pct_change": float(pct_change),
                    "volume": vol_val
                })
            except Exception:
                continue
    finally:
        conn.close()
    return tickers


def _read_hist_tickers_safe(etf_codes: list[str]) -> list[dict]:
    try:
        return _read_hist_tickers(etf_codes)
    except Exception:
        return []


@app.route("/api/trades")
def get_trades():
    db_file = _db_path()
    if not os.path.exists(db_file):
        return jsonify([])

    conn = sqlite3.connect(db_file)
    try:
        trades = pd.read_sql_query(
            "SELECT * FROM trades ORDER BY datetime(date) DESC LIMIT 200", conn
        )
    finally:
        conn.close()

    return jsonify(trades.to_dict("records"))


@app.route("/api/performance")
def get_performance():
    db_file = _db_path()
    use_trading = request.args.get("trading", "1") != "0"
    initial_capital = float(os.getenv("INITIAL_CAPITAL", "100000"))

    start_date_str = None
    try:
        perf_fp = os.path.join(_project_root(), "perf_start.json")
        if os.path.exists(perf_fp):
            with open(perf_fp, "r", encoding="utf-8") as f:
                _obj = json.load(f)
            start_date_str = _obj.get("start_date")
    except Exception:
        start_date_str = None

    if start_date_str:
        try:
            start_dt = pd.to_datetime(start_date_str)
        except Exception:
            start_dt = pd.to_datetime(pd.Timestamp.today().date())
    else:
        start_dt = pd.to_datetime(pd.Timestamp.today().date())

    end_dt = pd.to_datetime(pd.Timestamp.today().date())

    if not os.path.exists(db_file):
        full_idx = pd.date_range(start=start_dt, end=end_dt, freq="D")
        out_dates = [d.strftime("%Y-%m-%d") for d in full_idx]
        out_vals = [initial_capital for _ in out_dates]
        return jsonify({"dates": out_dates, "values": out_vals})

    conn = sqlite3.connect(db_file)
    try:
        try:
            deq = pd.read_sql_query("SELECT date, equity FROM daily_equity ORDER BY date", conn)
        except Exception:
            deq = pd.DataFrame()
        if not deq.empty:
            deq["date"] = pd.to_datetime(deq["date"]).dt.date
            series = pd.Series(deq["equity"].astype(float).values, index=pd.to_datetime(deq["date"]))
        else:
            try:
                trades = pd.read_sql_query("SELECT * FROM trades ORDER BY datetime(date)", conn)
            except Exception:
                trades = pd.DataFrame()
            if not trades.empty:
                trades["date"] = pd.to_datetime(trades["date"])  # 含时间
                daily = trades.groupby(trades["date"].dt.date)["capital_after"].last().reset_index()
                daily["date"] = pd.to_datetime(daily["date"]).dt.date
                series = pd.Series(daily["capital_after"].astype(float).values, index=pd.to_datetime(daily["date"]))
            else:
                series = pd.Series(dtype=float)

        trade_days = None
        try:
            etf_list_env = os.getenv("ETF_LIST", "").strip()
            etf_candidates = [x.strip() for x in etf_list_env.split(",") if x.strip()] if etf_list_env else []
            etf_db = _etf_db_path()
            if os.path.exists(etf_db):
                conn_etf = sqlite3.connect(etf_db)
                try:
                    table = None
                    if etf_candidates:
                        t = f"etf_{etf_candidates[0]}"
                        chk = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table' AND name=?", conn_etf, params=(t,))
                        if not chk.empty:
                            table = t
                    if table is None:
                        tbls = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'etf_%' ORDER BY name LIMIT 1", conn_etf)
                        if not tbls.empty:
                            table = tbls.iloc[0]["name"]
                    if table:
                        try:
                            df_cal = pd.read_sql_query(f"SELECT 日期 as d FROM {table} WHERE 日期 IS NOT NULL", conn_etf)
                        except Exception:
                            df_cal = pd.read_sql_query(f"SELECT date as d FROM {table} WHERE date IS NOT NULL", conn_etf)
                        if not df_cal.empty:
                            df_cal["d"] = pd.to_datetime(df_cal["d"]).dt.date
                            s = pd.Series(1, index=pd.to_datetime(df_cal["d"]))
                            trading_idx = s.loc[(s.index >= start_dt) & (s.index <= end_dt)].index
                            trade_days = pd.DatetimeIndex(sorted(trading_idx.unique()))
                finally:
                    conn_etf.close()
        except Exception:
            trade_days = None

        if use_trading and (trade_days is not None) and (len(trade_days) > 0):
            reindex_idx = trade_days
        else:
            reindex_idx = pd.date_range(start=start_dt, end=end_dt, freq="D")

        series = series.sort_index()
        series = series.reindex(reindex_idx)
        if series.isna().all():
            series[:] = initial_capital
        else:
            if pd.isna(series.iloc[0]):
                series.iloc[0] = initial_capital
            series = series.ffill()

        out_dates = [d.strftime("%Y-%m-%d") for d in series.index]
        out_vals = [float(v) if v == v else None for v in series.values]
        return jsonify({"dates": out_dates, "values": out_vals})
    finally:
        conn.close()


@app.route("/api/metrics")
def get_metrics():
    metrics = calculate_performance(_db_path())
    for k in list(metrics.keys()):
        try:
            metrics[k] = float(metrics[k]) if isinstance(metrics[k], (int, float)) else metrics[k]
        except Exception:
            pass
    return jsonify(metrics)


@app.route("/api/portfolio")
def get_portfolio():
    initial_capital = float(os.getenv("INITIAL_CAPITAL", "100000"))
    db_file = _db_path()
    cash = initial_capital
    positions: list[dict] = []
    holdings_value = 0.0

    if os.path.exists(db_file):
        conn = sqlite3.connect(db_file)
        try:
            try:
                tr = pd.read_sql_query("SELECT date, etf_code, action, quantity, capital_after FROM trades ORDER BY datetime(date)", conn)
            except Exception:
                tr = pd.DataFrame()
            if not tr.empty:
                if tr["capital_after"].notna().any():
                    cash = float(tr["capital_after"].dropna().iloc[-1])
                qty: dict[str, float] = {}
                for _, r in tr.iterrows():
                    code = str(r.get("etf_code") or "").strip()
                    if not code:
                        continue
                    q = float(r.get("quantity") or 0.0)
                    if str(r.get("action")).lower() == "sell":
                        q = -q
                    qty[code] = qty.get(code, 0.0) + q
                for code, qv in qty.items():
                    if abs(qv) < 1e-9:
                        continue
                    px = _read_latest_price(code)
                    if px is None:
                        continue
                    val = float(qv) * float(px)
                    holdings_value += val
                    positions.append({
                        "etf_code": code,
                        "quantity": float(qv),
                        "price": float(px),
                        "value": float(val),
                    })
        finally:
            conn.close()

    total_value = float(cash) + float(holdings_value)
    return jsonify({
        "cash": float(cash),
        "holdings_value": float(holdings_value),
        "total_value": float(total_value),
        "positions": positions,
    })


def _get_current_holdings() -> set:
    """从交易历史计算当前持仓的ETF代码集合"""
    db_file = _db_path()
    holdings = set()
    if not os.path.exists(db_file):
        return holdings

    conn = sqlite3.connect(db_file)
    try:
        tr = pd.read_sql_query("SELECT etf_code, action, quantity FROM trades ORDER BY datetime(date)", conn)
        if not tr.empty:
            qty: dict[str, float] = {}
            for _, r in tr.iterrows():
                code = str(r.get("etf_code") or "").strip()
                if not code:
                    continue
                q = float(r.get("quantity") or 0.0)
                if str(r.get("action")).lower() == "sell":
                    q = -q
                qty[code] = qty.get(code, 0.0) + q
            
            for code, qv in qty.items():
                if qv > 1e-9:
                    holdings.add(code)
    except Exception:
        pass
    finally:
        conn.close()
    return holdings


@app.route("/api/decisions")
def get_decisions():
    decisions_dir = os.path.join(_project_root(), "decisions")
    if not os.path.isdir(decisions_dir):
        return jsonify([])

    current_holdings = _get_current_holdings()
    rows: List[Dict[str, Any]] = []
    for fpath in glob.glob(os.path.join(decisions_dir, "*.json")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                d = json.load(f)
            base = os.path.basename(fpath)
            name_no_ext = os.path.splitext(base)[0]
            parts = name_no_ext.split("_")
            date = parts[0] if parts else ""
            etf = parts[1] if len(parts) > 1 else ""
            rows.append({
                    "file": base,
                    "date": date,
                    "etf": etf,
                    "decision": d.get("decision"),
                    "confidence": d.get("confidence"),
                    "reasoning": d.get("reasoning"),
                    "is_holding": etf in current_holdings,
            })
        except Exception:
            continue

    rows.sort(key=lambda x: x.get("date", ""), reverse=True)
    return jsonify(rows[:100])


@app.route("/api/qlib/factors")
def get_qlib_factors():
    base_dir = os.path.join(_project_root(), "data", "qlib_factors")
    if not os.path.isdir(base_dir):
        return jsonify([])

    code = (request.args.get("code") or "").strip()
    try:
        limit = int(request.args.get("limit", "50"))
    except Exception:
        limit = 50

    # Get strategy configuration from environment
    strategy_mode = os.getenv("STRATEGY_MODE", "MA_CROSS")
    strategy_config = {
        "mode": strategy_mode,
        "breakout_n": int(os.getenv("BREAKOUT_N", "20")),
        "rsi_n": int(os.getenv("RSI_N", "2")),
        "rsi_low": int(os.getenv("RSI_LOW", "10")),
        "rsi_high": int(os.getenv("RSI_HIGH", "95")),
    }

    def read_one(code_: str, limit_: int | None = None):
        fp = os.path.join(base_dir, f"{code_}.csv")
        if not os.path.exists(fp):
            return []
        try:
            df = pd.read_csv(fp)
        except Exception:
            return []
        if df.empty:
            return []
        try:
            df["date"] = pd.to_datetime(df["date"])  # type: ignore
        except Exception:
            pass
        df = df.sort_values("date", ascending=False)
        if limit_ is not None:
            df = df.head(limit_)
        out = []
        for _, r in df.iterrows():
            out.append({
                "date": str(r.get("date")),
                "symbol": r.get("symbol"),
                "ret_1d_pct": float(r.get("ret_1d_pct")) if pd.notna(r.get("ret_1d_pct")) else None,
                "vol_20d_pct": float(r.get("vol_20d_pct")) if pd.notna(r.get("vol_20d_pct")) else None,
                "rsi_14": float(r.get("rsi_14")) if pd.notna(r.get("rsi_14")) else None,
                "strategy": strategy_config,
            })
        return out

    if code:
        return jsonify(read_one(code, limit))

    codes_env = [x.strip() for x in (os.getenv("ETF_LIST", "").split(",") if os.getenv("ETF_LIST") else []) if x.strip()]
    out_latest = []
    for c in codes_env:
        rows = read_one(c, 1)
        if rows:
            out_latest.append(rows[0])
    return jsonify(out_latest)


@app.route("/api/vega_risk")
def get_vega_risk():
    try:
        from src.vegas import compute_vega_proxy_series, latest_summary
    except Exception:
        return jsonify({"ok": False, "msg": "vegas 模块不可用"}), 500

    code = (request.args.get("code") or "").strip()
    try:
        period = int(request.args.get("period", "60"))
    except Exception:
        period = 60
    try:
        vol_lb = int(os.getenv("VEGAS_VOL_LOOKBACK", "20"))
    except Exception:
        vol_lb = 20
    try:
        t_days = int(os.getenv("VEGAS_T_DAYS", "30"))
    except Exception:
        t_days = 30

    if code:
        df = compute_vega_proxy_series(code, vol_lb, t_days, period)
        if df is None or df.empty:
            return jsonify({"code": code, "rows": []})
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "date": str(r.get("date")),
                "S": float(r.get("S")) if pd.notna(r.get("S")) else None,
                "sigma": float(r.get("sigma")) if pd.notna(r.get("sigma")) else None,
                "vega_proxy": float(r.get("vega_proxy")) if pd.notna(r.get("vega_proxy")) else None,
                "delta_sigma": float(r.get("delta_sigma")) if pd.notna(r.get("delta_sigma")) else None,
                "delta_V": float(r.get("delta_V")) if pd.notna(r.get("delta_V")) else None,
                "cum_delta_V": float(r.get("cum_delta_V")) if pd.notna(r.get("cum_delta_V")) else None,
            })
        return jsonify({"code": code, "rows": rows})

    codes_env = [x.strip() for x in (os.getenv("ETF_LIST", "").split(",") if os.getenv("ETF_LIST") else []) if x.strip()]
    if not codes_env:
        return jsonify([])
    try:
        rows = latest_summary(codes_env, vol_lb, t_days)
    except Exception:
        rows = []
    return jsonify(rows)


def _risk_free_rate() -> float:
    try:
        return float(os.getenv("RISK_FREE_RATE", "0.02"))
    except Exception:
        return 0.02


def _try_fetch_option_chain_from_ak(code: str):
    """调用 src.options.try_fetch_option_chain_from_ak 抓取ETF期权链。
    返回 (DataFrame, msg)。成功时 msg=None；失败时 DataFrame=None 并带错误信息。
    """
    try:
        from src.options import try_fetch_option_chain_from_ak as _impl
    except Exception as e:
        return None, f"期权模块不可用: {e}"
    try:
        days = int(os.getenv("OPT_MAX_EXPIRY_DAYS", "30"))
    except Exception:
        days = 30
    try:
        df = _impl(code, max_expiry_days=days)
        if df is None or df.empty:
            return None, "未获取到期权链"
        return df, None
    except Exception as e:
        return None, f"期权链拉取异常: {e}"


# ---- Simple in-memory cache for options endpoints ----
_OPT_CACHE: dict = {}

def _opt_cache_ttl() -> int:
    try:
        return int(os.getenv("OPT_CACHE_TTL", "60"))
    except Exception:
        return 60

def _cache_get(key):
    ent = _OPT_CACHE.get(key)
    if not ent:
        return None
    if ent["exp"] < _time():
        try:
            del _OPT_CACHE[key]
        except Exception:
            pass
        return None
    return ent["val"]

def _cache_set(key, val, ttl: int):
    _OPT_CACHE[key] = {"exp": _time() + max(1, int(ttl)), "val": val}


@app.route("/api/options/chain")
def get_options_chain():
    code = (request.args.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "msg": "缺少code参数"}), 400
    ttl = _opt_cache_ttl()
    cache_key = ("opt_chain", code, int(os.getenv("OPT_MAX_EXPIRY_DAYS", "30") or 30))
    cached = _cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)
    df, msg = _try_fetch_option_chain_from_ak(code)
    if df is None or (hasattr(df, "empty") and df.empty):
        resp = {"ok": False, "code": code, "msg": msg or "未获取到期权链"}
        _cache_set(cache_key, resp, ttl)
        return jsonify(resp), 200
    # 期望返回字段：opt_type, K, expiry, T_days, price_mid, iv, greeks{delta,gamma,vega,theta}
    from src.options import implied_vol, greeks as bs_greeks
    try:
        S = _read_latest_price(code) or 0.0
        r = _risk_free_rate()
        q = 0.0
        rows = []
        for _, r0 in df.iterrows():
            try:
                opt_type = str(r0.get("option_type", r0.get("type", "call")).lower())
                K = float(r0.get("strike", r0.get("K", 0)))
                mid = float(r0.get("mid", (float(r0.get("bid", 0))+float(r0.get("ask", 0)))/2 or 0))
                expiry = str(r0.get("expiry", r0.get("maturity", "")))
                # 计算到期天数（占位：如果无到期，跳过）
                T_days = None
                try:
                    if expiry:
                        dt = pd.to_datetime(expiry).to_pydatetime()
                        T_days = max(0, (dt - datetime.now()).days)
                except Exception:
                    T_days = None
                if not (S and K and mid and T_days and T_days > 0):
                    continue
                T = T_days / 365.0
                iv = implied_vol(S, K, T, r, q, mid, opt_type=opt_type)
                g = bs_greeks(S, K, T, r, q, iv if iv==iv else 0.3, opt_type=opt_type)
                rows.append({
                    "opt_type": opt_type,
                    "K": K,
                    "expiry": expiry,
                    "T_days": T_days,
                    "price_mid": mid,
                    "iv": iv if iv==iv else None,
                    "delta": g.get("delta"),
                    "gamma": g.get("gamma"),
                    "vega": g.get("vega"),
                    "theta": g.get("theta"),
                })
            except Exception:
                continue
        resp = {"ok": True, "code": code, "rows": rows}
        _cache_set(cache_key, resp, ttl)
        return jsonify(resp)
    except Exception as e:
        return jsonify({"ok": False, "code": code, "msg": f"处理期权链异常: {e}"}), 500


@app.route("/api/options/atm_iv")
def get_options_atm_iv():
    code = (request.args.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "msg": "缺少code参数"}), 400
    ttl = _opt_cache_ttl()
    cache_key = ("opt_atm", code, int(os.getenv("OPT_MAX_EXPIRY_DAYS", "30") or 30))
    cached = _cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    df, msg = _try_fetch_option_chain_from_ak(code)
    if df is None or (hasattr(df, "empty") and df.empty):
        resp = {"ok": False, "code": code, "msg": msg or "未获取到期权链"}
        _cache_set(cache_key, resp, ttl)
        return jsonify(resp), 200
    try:
        S = _read_latest_price(code) or 0.0
        if S <= 0:
            resp = {"ok": False, "code": code, "msg": "无法读取标的现价"}
            _cache_set(cache_key, resp, ttl)
            return jsonify(resp), 200
        # 选择行权价最接近S的一组
        df2 = df.copy()
        strike_col = None
        for c in ("strike", "K"):
            if c in df2.columns:
                strike_col = c
                break
        if strike_col is None:
            resp = {"ok": False, "code": code, "msg": "期权链缺少行权价列"}
            _cache_set(cache_key, resp, ttl)
            return jsonify(resp), 200
        df2["_dist"] = (pd.to_numeric(df2[strike_col], errors="coerce")-S).abs()
        df2 = df2.sort_values("_dist").head(6)  # 附近若干
        r = _risk_free_rate(); q = 0.0
        from src.options import implied_vol
        out = []
        for _, r0 in df2.iterrows():
            try:
                opt_type = str(r0.get("option_type", r0.get("type", "call")).lower())
                K = float(r0.get(strike_col))
                mid = float(r0.get("mid", (float(r0.get("bid", 0))+float(r0.get("ask", 0)))/2 or 0))
                expiry = str(r0.get("expiry", r0.get("maturity", "")))
                T_days = None
                try:
                    if expiry:
                        dt = pd.to_datetime(expiry).to_pydatetime(); T_days = max(0, (dt - datetime.now()).days)
                except Exception:
                    T_days = None
                if not (S and K and mid and T_days and T_days > 0):
                    continue
                T = T_days/365.0
                iv = implied_vol(S, K, T, r, q, mid, opt_type=opt_type)
                out.append({"opt_type": opt_type, "K": K, "expiry": expiry, "T_days": T_days, "mid": mid, "iv": iv if iv==iv else None})
            except Exception:
                continue
        resp = {"ok": True, "code": code, "rows": out}
        _cache_set(cache_key, resp, ttl)
        return jsonify(resp)
    except Exception as e:
        return jsonify({"ok": False, "code": code, "msg": f"ATM IV 处理异常: {e}"}), 500


@app.route("/api/qlib/status")
def qlib_status():
    raw_dir = os.path.abspath(os.path.join(_project_root(), "data", "qlib", "raw"))
    provider_dir = os.path.abspath(QLIB_DIR)
    try:
        raw_cnt = len([f for f in os.listdir(raw_dir) if f.endswith('.csv')]) if os.path.isdir(raw_dir) else 0
    except Exception:
        raw_cnt = 0
    return jsonify({
        "installed": _qlib_installed(),
        "enabled": QLIB_ENABLED,
        "inited": QLIB_INITED,
        "region": QLIB_REGION,
        "provider_dir": provider_dir,
        "provider_exists": os.path.isdir(provider_dir),
        "raw_csv_count": raw_cnt,
        "error": QLIB_ERROR,
    })


@app.route("/api/etf_tickers_source")
def get_ticker_source():
    try:
        src = globals().get("_LAST_TICKER_SOURCE", "unknown")
    except Exception:
        src = "unknown"
    return jsonify({"source": src})

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("FLASK_PORT", "5000"))
    except Exception:
        port = 5000
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)
