# -*- coding: utf-8 -*-
from __future__ import annotations
"""
主任务调度：
- 每日收盘后执行：拉取数据 -> 风控检查 -> 获取AI决策(限流/缓存/重试) -> 规则信号 -> 合议 -> 执行交易 -> 打印账户总资产
- 启动时先立即执行一次 daily_task()
运行方式（确保在项目根目录）：
    python -m src.main
支持 .env 配置：
- CORE_ETF_LIST / OBSERVE_ETF_LIST / ETF_LIST
- SCHEDULE_TIME=17:00
- DAILY_AI_CALLS_LIMIT=3
- ENABLE_ENSEMBLE=true/false（默认 false）
- ENSEMBLE_MODE=CONSENSUS（目前仅实现一致同意：AI 与 规则同向才下单，否则 hold）
"""
import glob
import logging
import os
import sqlite3
from datetime import datetime

import pandas as pd
import schedule
import time as tm
from dotenv import load_dotenv

from src.data_fetcher import fetch_etf_data, save_to_db
from src.ai_decision import get_ai_decision
from src.trade_executor import TradeExecutor


# ---------------- Config helpers ----------------

def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def _etf_db_path() -> str:
    return os.path.join(_project_root(), "data", "etf_data.db")


def _decisions_dir() -> str:
    return os.path.join(_project_root(), "decisions")


def _parse_etf_list(env_val: str | None, default: list[str]) -> list[str]:
    if not env_val:
        return default
    items = [x.strip() for x in env_val.split(",") if x.strip()]
    return items or default

def filter_etf_pool(etf_list: list[str]) -> list[str]:
    """
    根据流动性（日均成交额）和上市时间过滤ETF标的池
    """
    logger = logging.getLogger("main")
    try:
        filter_enabled = os.getenv("FILTER_ENABLED", "true").lower() == "true"
        if not filter_enabled:
            logger.info("标的池过滤未启用。")
            return etf_list

        min_avg_turnover = float(os.getenv("MIN_AVG_TURNOVER", "10000000"))  # 默认1000万
        min_listing_months = int(os.getenv("MIN_LISTING_MONTHS", "6"))
        turnover_lookback_days = 20
    except (ValueError, TypeError) as e:
        logger.warning(f"解析过滤参数失败: {e}，跳过过滤。")
        return etf_list

    logger.info(f"开始过滤标的池... 最小成交额: {min_avg_turnover/10000:.0f}万, 最短上市: {min_listing_months}月")

    try:
        import akshare as ak
        etf_info_df = ak.fund_etf_fund_info_em()
    except Exception as e:
        logger.warning(f"无法从akshare获取ETF基本信息: {e}，跳过过滤。")
        return etf_list

    filtered_list = []
    for code in etf_list:
        try:
            # 1. 上市日期检查
            info = etf_info_df[etf_info_df['基金代码'] == code]
            if info.empty:
                logger.debug(f"{code}: 未在ETF信息列表中找到，跳过。")
                continue
            
            listing_date_str = info.iloc[0]['上市日期']
            listing_date = pd.to_datetime(listing_date_str)
            months_since_listing = (datetime.now() - listing_date).days / 30.44
            if months_since_listing < min_listing_months:
                logger.info(f"{code}: 上市时间（{months_since_listing:.1f}月）不足 {min_listing_months}月，已过滤。")
                continue

            # 2. 流动性检查
            hist_df = fetch_etf_data(code, days=turnover_lookback_days + 5) # 多取几天以防节假日
            if hist_df.empty or len(hist_df) < turnover_lookback_days:
                logger.info(f"{code}: 历史数据不足，无法计算流动性，已过滤。")
                continue

            turnover_col = next((c for c in ["成交额", "turnover"] if c in hist_df.columns), None)
            if not turnover_col:
                logger.warning(f"{code}: 缺少成交额数据，无法进行流动性过滤。")
                filtered_list.append(code) # 无法判断则暂时放行
                continue

            avg_turnover = hist_df[turnover_col].tail(turnover_lookback_days).mean()
            if avg_turnover < min_avg_turnover:
                logger.info(f"{code}: 最近{turnover_lookback_days}日均成交额({avg_turnover/10000:.0f}万)过低，已过滤。")
                continue
            
            filtered_list.append(code)

        except Exception as e:
            logger.warning(f"过滤 {code} 时出错: {e}，默认保留。")
            if code not in filtered_list:
                 filtered_list.append(code)

    logger.info(f"标的池过滤完成，剩余 {len(filtered_list)}/{len(etf_list)} 个标的: {','.join(filtered_list)}")
    return filtered_list


# ---------------- Prices helpers ----------------

def _read_latest_price(etf_code: str) -> float | None:
    db_file = _etf_db_path()
    if not os.path.exists(db_file):
        return None
    conn = sqlite3.connect(db_file)
    try:
        df = pd.read_sql_query(f"SELECT * FROM etf_{etf_code} ORDER BY 日期 DESC LIMIT 1", conn)
    except Exception:
        try:
            df = pd.read_sql_query(f"SELECT * FROM etf_{etf_code} ORDER BY date DESC LIMIT 1", conn)
        except Exception:
            df = pd.DataFrame()
    finally:
        conn.close()

    if df.empty:
        return None

    for col in ("收盘", "收盘价", "close", "Close"):
        if col in df.columns:
            try:
                return float(df.iloc[0][col])
            except Exception:
                continue
    return None


# ---------------- Rule-based Signals ----------------

def get_rule_decision(df: pd.DataFrame, params: dict, etf_code: str | None = None) -> dict:
    df = df.copy()
    mode = params.get("mode", "MA_CROSS").upper()
    signals = []

    def _find_col(*args):
        for c in args:
            if c in df.columns:
                return c
        return None

    close_col = _find_col("收盘", "收盘价", "close", "Close")
    high_col = _find_col("最高", "最高价", "high", "High")
    low_col = _find_col("最低", "最低价", "low", "Low")

    if not close_col:
        return {"decision": "hold", "reasoning": "规则：无收盘价数据", "confidence": 0.5}

    close = df[close_col]
    latest_close = close.iloc[-1]

    def _ma_cross():
        if len(df) < 61:
            return None
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        if (ma20.iloc[-2] <= ma60.iloc[-2]) and (ma20.iloc[-1] > ma60.iloc[-1]) and (latest_close > ma20.iloc[-1]):
            return {"decision": "buy", "reasoning": "规则：MA20上穿MA60", "confidence": 0.6}
        if (ma20.iloc[-2] >= ma60.iloc[-2]) and (ma20.iloc[-1] < ma60.iloc[-1]) and (latest_close < ma20.iloc[-1]):
            return {"decision": "sell", "reasoning": "规则：MA20下穿MA60", "confidence": 0.6}
        return None

    def _breakout():
        if not high_col or not low_col:
            return None
        n = params.get("breakout_n", 20)
        if len(df) < n + 1:
            return None
        donchian_high = df[high_col].rolling(n).max().shift(1)
        if latest_close > donchian_high.iloc[-1]:
            return {"decision": "buy", "reasoning": f"规则：突破{n}日高点", "confidence": 0.65}
        return None

    def _mean_reversion():
        n = params.get("rsi_n", 2)
        if len(df) < n + 1:
            return None
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=n).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=n).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        if rsi.iloc[-1] < params.get("rsi_low", 10):
            return {"decision": "buy", "reasoning": f"规则：RSI({n})超卖", "confidence": 0.7}
        if rsi.iloc[-1] > params.get("rsi_high", 95):
            return {"decision": "sell", "reasoning": f"规则：RSI({n})超买", "confidence": 0.7}
        return None

    def _kdj_macd_signal():
        if not all(c in df.columns for c in ['k', 'd', 'j', 'dif', 'dea', 'macd']):
            return None
        
        kdj_low = params.get("kdj_low", 20)
        
        j_cross_up = (df['j'].iloc[-2] < kdj_low) and (df['j'].iloc[-1] > kdj_low)
        macd_cross_up = (df['dif'].iloc[-2] < df['dea'].iloc[-2]) and (df['dif'].iloc[-1] > df['dea'].iloc[-1])
        
        if j_cross_up and macd_cross_up:
            return {"decision": "buy", "reasoning": f"规则：KDJ探底(J>{kdj_low}) + MACD金叉", "confidence": 0.75}
        
        return None

    if mode == "MA_CROSS":
        s = _ma_cross()
        if s: signals.append(s)
    elif mode == "BREAKOUT":
        s = _breakout()
        if s: signals.append(s)
    elif mode == "MEAN_REVERSION":
        s = _mean_reversion()
        if s: signals.append(s)
    elif mode == "KDJ_MACD":
        s = _kdj_macd_signal()
        if s: signals.append(s)
    elif mode == "AGGRESSIVE":
        def _qlib_factor_rule():
            try:
                if os.getenv("QLIB_FACTOR_ENABLED", "true").lower() != "true":
                    return None
                if etf_code is None:
                    return None
                fac_fp = os.path.join(_project_root(), "data", "qlib_factors", f"{etf_code}.csv")
                if not os.path.exists(fac_fp):
                    return None
                q = pd.read_csv(fac_fp)
                if q.empty:
                    return None
                try:
                    q["date"] = pd.to_datetime(q["date"])  # type: ignore
                    q = q.sort_values("date")
                except Exception:
                    pass
                r = q.iloc[-1]
                rsi14 = float(r.get("rsi_14")) if pd.notna(r.get("rsi_14")) else None
                if rsi14 is None:
                    return None
                low_thr = float(os.getenv("QLIB_RSI_LOW", "30"))
                high_thr = float(os.getenv("QLIB_RSI_HIGH", "70"))
                if rsi14 < low_thr:
                    return {"decision": "buy", "reasoning": f"Qlib因子: RSI14<{low_thr}", "confidence": 0.6}
                if rsi14 > high_thr:
                    return {"decision": "sell", "reasoning": f"Qlib因子: RSI14>{high_thr}", "confidence": 0.6}
                return None
            except Exception:
                return None
        fn_list = [_breakout, _mean_reversion, _ma_cross, _kdj_macd_signal]
        if os.getenv("QLIB_FACTOR_ENABLED", "true").lower() == "true":
            fn_list.append(_qlib_factor_rule)
        for fn in fn_list:
            s = fn()
            if s: signals.append(s)

    if not signals:
        return {"decision": "hold", "reasoning": "规则：无信号", "confidence": 0.5}

    signals.sort(key=lambda x: (x["decision"] != 'buy', x["decision"] != 'sell', -x.get("confidence", 0)))
    return signals[0]


def validate_decision(decision: dict, price: float) -> dict:
    """轻量校验/填充决策字段，避免下游 NameError/KeyError。
    当前仅做字段兜底；复杂规则校验可后续增强。
    """
    out = dict(decision) if isinstance(decision, dict) else {"decision": "hold"}
    out.setdefault("decision", "hold")
    try:
        out["confidence"] = float(out.get("confidence", 0.5))
    except Exception:
        out["confidence"] = 0.5
    if "reasoning" not in out:
        out["reasoning"] = ""
    return out


def ensemble_decision(ai_dec: dict, rule_dec: dict, mode: str = "CONSENSUS") -> dict:
    if mode.upper() != "CONSENSUS":
        return ai_dec
    ai = (ai_dec or {}).get("decision", "hold")
    rl = (rule_dec or {}).get("decision", "hold")
    if ai == rl and ai in ("buy", "sell"):
        reason = f"合议一致：AI({ai_dec.get('confidence')}) {ai_dec.get('reasoning')} | 规则({rule_dec.get('confidence')}) {rule_dec.get('reasoning')}"
        conf = (float(ai_dec.get("confidence", 0.5)) + float(rule_dec.get("confidence", 0.5))) / 2.0
        merged = dict(ai_dec)
        merged.update({"reasoning": reason, "confidence": conf})
        return merged
    return {
        "decision": "hold",
        "confidence": 0.5,
        "reasoning": f"合议分歧：AI={ai}，规则={rl}，默认持有",
        "stop_loss": None,
        "take_profit": None,
    }


# ---------------- Main daily task ----------------

def daily_task(executor: TradeExecutor, core_list: list[str], observe_list: list[str], daily_ai_limit: int, force_date: Optional[datetime.date] = None):
    logger = logging.getLogger("main")
    logger.info("=== %s 每日任务开始 ===", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # --- 1. 数据准备 (合并所有列表以统一拉取) ---
    all_etfs = sorted(list(set(core_list + observe_list)))
    for etf in all_etfs:
        try:
            df = fetch_etf_data(etf, days=700, end_date=force_date.strftime("%Y%m%d") if force_date else None)
            save_to_db(df, etf, db_path=_etf_db_path())
            logger.info(f"已更新 {etf} 数据{' (截至 ' + force_date.strftime('%Y-%m-%d') + ')' if force_date else ''}")
        except Exception as e:
            logger.warning(f"更新 {etf} 失败: {e}")

    current_prices: dict[str, float] = {}
    latest_dfs: dict[str, pd.DataFrame] = {}
    db_file = _etf_db_path()
    for etf in all_etfs:
        price = _read_latest_price(etf)
        if price is not None:
            current_prices[etf] = price
        
        if os.path.exists(db_file):
            conn = sqlite3.connect(db_file)
            try:
                df = pd.read_sql_query(f"SELECT * FROM etf_{etf} ORDER BY 日期 ASC", conn)
            except Exception:
                df = pd.DataFrame()
            finally:
                conn.close()
            if not df.empty:
                latest_dfs[etf] = df.tail(200)
                if etf not in current_prices:
                    px = df.iloc[-1].get('收盘', df.iloc[-1].get('close'))
                    if pd.notna(px):
                        current_prices[etf] = float(px)

    executor.auto_risk_sell(current_prices)

    # --- Qlib TopK (optional rule source) ---
    qlib_topk_set = None
    try:
        if os.getenv("QLIB_ALGO_ENABLED", "false").lower() == "true":
            provider = os.path.abspath(os.getenv("QLIB_DIR", os.path.join(_project_root(), "data", "qlib", "cn_etf")))
            region = os.getenv("QLIB_REGION", "cn")
            lookback = int(os.getenv("QLIB_TOPK_LOOKBACK", "60"))
            topk_k = int(os.getenv("QLIB_TOPK_K", "2"))
            import qlib  # type: ignore
            from qlib.data import D  # type: ignore
            qlib.init(provider_uri=provider, region=region)
            # compute topK set
            import pandas as _pd
            from datetime import date as _date, timedelta as _td
            end = _date.today(); start = end - _td(days=max(lookback*2, lookback+30))
            df_feat = D.features(all_etfs, ["$close"], start_time=str(start), end_time=str(end))
            if df_feat is not None and not df_feat.empty:
                df_feat = df_feat.dropna()
                dates = sorted(df_feat.index.get_level_values(0).unique())
                if len(dates) >= 2:
                    last_day = dates[-1]
                    first_day = dates[-lookback] if len(dates) >= lookback else dates[0]
                    today_close = df_feat.xs(last_day, level=0)["$close"]
                    base_close = df_feat.xs(first_day, level=0)["$close"]
                    common = today_close.index.intersection(base_close.index)
                    ret = (today_close.loc[common] / base_close.loc[common] - 1.0).sort_values(ascending=False)
                    qlib_topk_set = set(ret.head(topk_k).index.tolist())
    except Exception:
        qlib_topk_set = None

    # --- 2. 决策生成 (分层处理) ---
    decisions_to_execute = {}
    core_buy_signal_found = False
    ai_calls_this_run = 0

    def _process_etf(etf: str):
        nonlocal ai_calls_this_run
        df = latest_dfs.get(etf)
        if df is None or df.empty:
            logger.warning("%s 无足够数据，跳过决策", etf)
            return None

        # 1) 规则信号
        strategy_mode = os.getenv("STRATEGY_MODE", "AGGRESSIVE")
        rule_params = {
            "mode": strategy_mode,
            "breakout_n": int(os.getenv("BREAKOUT_N", "20")),
            "rsi_n": int(os.getenv("RSI_N", "2")),
            "rsi_low": int(os.getenv("RSI_LOW", "10")),
            "rsi_high": int(os.getenv("RSI_HIGH", "95")),
            "kdj_low": int(os.getenv("KDJ_LOW", "20")),
        }
        rd = get_rule_decision(df, rule_params, etf_code=etf)

        # 可选：Qlib TopK 融合到规则（若开启则提升/覆盖规则）
        if qlib_topk_set is not None:
            if etf in qlib_topk_set:
                rd = {"decision": "buy", "confidence": max(0.7, float(rd.get("confidence", 0.6))),
                      "reasoning": (rd.get("reasoning", "") + " | Qlib TopK")[:512]}
            else:
                # 仅当原规则为 hold 时，给出温和的 sell 提示
                if rd.get("decision") == "hold":
                    rd = {"decision": "sell", "confidence": 0.6, "reasoning": "Qlib 非TopK"}

        # 2) AI 决策（限流）
        ai_dec = {"decision": "hold", "confidence": 0.5, "reasoning": "AI限流或异常"}
        try:
            if ai_calls_this_run < daily_ai_limit:
                from src.ai_decision import get_ai_decision as _ai
                ai_dec = _ai(etf, df, force_date=force_date)
                ai_calls_this_run += 1
            else:
                logger.info("已达当日AI调用上限(%s)，%s 使用默认持有策略", daily_ai_limit, etf)
        except Exception as e:
            logger.warning("AI决策失败，%s 使用规则策略：%s", etf, e)

        # 3) 合议
        final_decision = ensemble_decision(ai_dec, rd, os.getenv("ENSEMBLE_MODE", "CONSENSUS"))
        px_for_val = current_prices.get(etf, 0.0)
        final_decision = validate_decision(final_decision, px_for_val)
        return etf, final_decision

    # --- 2a. 核心池决策 ---
    logger.info(f"--- 开始处理核心池 ({len(core_list)}个) ---")
    for etf in core_list:
        result = _process_etf(etf)
        if result:
            decisions_to_execute[result[0]] = result[1]
            if result[1].get('decision') == 'buy':
                core_buy_signal_found = True

    # --- 2b. 观察池决策 (仅当核心池无买入信号时) ---
    if not core_buy_signal_found and observe_list:
        logger.info(f"--- 核心池无买入信号，开始处理观察池 ({len(observe_list)}个) ---")
        for etf in observe_list:
            result = _process_etf(etf)
            if result:
                decisions_to_execute[result[0]] = result[1]
    elif observe_list:
        logger.info("--- 核心池已产生买入信号，跳过观察池。 ---")

    # --- 3. 统一执行交易 ---
    logger.info("--- 开始执行所有决策 ---")
    for etf, decision in decisions_to_execute.items():
        if etf in current_prices:
            executor.execute_trade(etf, decision, current_prices[etf])

    # ... (后续总资产计算和快照写入逻辑) ...

    # --- 4. 写入日终快照（带明细日志） ---
    # 计算持仓估值明细，便于排查异常净值
    try:
        holdings_value = 0.0
        missing_px = []
        if getattr(executor, 'positions', None):
            for code, pos in executor.positions.items():
                qty = float(pos.get('quantity', 0) or 0)
                px = float(current_prices.get(code, 0) or 0)
                if px <= 0:
                    missing_px.append(code)
                val = qty * (px if px > 0 else 0)
                holdings_value += val
                logger.info(f"[equity-breakdown] {code} qty={qty:.4f} px={px:.4f} val={val:.2f}")
        logger.info(f"[equity-breakdown] cash={executor.capital:.2f} holdings={holdings_value:.2f} missing_px={missing_px}")
    except Exception:
        pass

    final_equity = executor.get_portfolio_value(current_prices)
    snapshot_date = force_date if force_date else datetime.now().date()
    try:
        conn = sqlite3.connect(executor.db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")
        conn.execute(
            "INSERT INTO daily_equity(date, equity) VALUES(?,?) ON CONFLICT(date) DO UPDATE SET equity=excluded.equity",
            (snapshot_date.strftime("%Y-%m-%d"), final_equity),
        )
        conn.commit()
        logger.info(f"已写入日终快照 {snapshot_date.strftime('%Y-%m-%d')}: {final_equity:.2f}")
    except Exception as e:
        logger.error(f"写入日终快照失败: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    logger.info("=== 每日任务结束 ===\n")


def _setup_logging():
    """Initialize console and file logging consistent with daily_once."""
    logs_dir = os.path.join(_project_root(), "logs")
    _ensure_dir(logs_dir)
    log_file = os.path.join(logs_dir, "daily.log")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # console
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    # file
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    logger.handlers = []
    logger.addHandler(ch)
    logger.addHandler(fh)

if __name__ == "__main__":
    # Minimal runnable entrypoint (not used by daily_once import). Run once and optional schedule.
    load_dotenv(override=True)
    _setup_logging()

    default_etfs = ["510050", "159915", "510300"]
    core_env = os.getenv("CORE_ETF_LIST", os.getenv("ETF_LIST"))
    core_etfs = _parse_etf_list(core_env, default_etfs)
    observe_etfs = _parse_etf_list(os.getenv("OBSERVE_ETF_LIST"), [])

    core_etfs = filter_etf_pool(core_etfs)
    observe_etfs = filter_etf_pool(observe_etfs)

    try:
        daily_ai_limit = int(os.getenv("DAILY_AI_CALLS_LIMIT", str(len(core_etfs) + len(observe_etfs))))
    except Exception:
        daily_ai_limit = len(core_etfs) + len(observe_etfs)

    try:
        init_cap = float(os.getenv("INITIAL_CAPITAL", "100000"))
    except Exception:
        init_cap = 100000.0
    executor = TradeExecutor(initial_capital=init_cap)

    # run once immediately
    daily_task(executor, core_etfs, observe_etfs, daily_ai_limit)

    # optional schedule
    schedule_time = os.getenv("SCHEDULE_TIME", "")
    if schedule_time:
        schedule.every().day.at(schedule_time).do(daily_task, executor, core_etfs, observe_etfs, daily_ai_limit)
        while True:
            schedule.run_pending()
            tm.sleep(1)
