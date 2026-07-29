# -*- coding: utf-8 -*-
from __future__ import annotations
"""
Lightweight in-memory backtest engine (rule-only by default).
- Does NOT write to trade_history.db
- Reads historical daily close from data/etf_data.db
- Uses src.main.get_rule_decision to generate rule signals
- Simple executor: buy all-in at base position when buy, sell all when sell
- Returns equity curve, KPIs, trades, and daily trade counts
"""
import os
import sqlite3
from typing import Dict, Any, List, Tuple
from datetime import datetime, date

import pandas as pd
import numpy as np

from dotenv import load_dotenv

# Reuse rule decision
from src.main import get_rule_decision

load_dotenv(override=True)


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _etf_db_path() -> str:
    return os.path.join(_project_root(), "data", "etf_data.db")


def _read_series(code: str) -> pd.DataFrame:
    """Read full daily series for code: returns DataFrame with columns ['date','close'] ascending."""
    db = _etf_db_path()
    if not os.path.exists(db):
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        df = pd.DataFrame()
        for q in (
            f"SELECT * FROM etf_{code} ORDER BY 日期 ASC",
            f"SELECT * FROM etf_{code} ORDER BY date ASC",
        ):
            try:
                df = pd.read_sql_query(q, conn)
                if not df.empty:
                    break
            except Exception:
                continue
    finally:
        conn.close()
    if df.empty:
        return df
    # normalize
    dcol = None
    for c in ("日期", "date", "Date"):
        if c in df.columns:
            dcol = c; break
    ccol = None
    for c in ("收盘", "收盘价", "close", "Close"):
        if c in df.columns:
            ccol = c; break
    if dcol is None or ccol is None:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(df[dcol], errors="coerce"),
        "close": pd.to_numeric(df[ccol], errors="coerce"),
    }).dropna().sort_values("date").reset_index(drop=True)
    return out


class _BTExecutor:
    def __init__(self, initial_capital: float, cost_bps: float, slip_bps: float):
        self.cash = float(initial_capital)
        self.positions: Dict[str, Dict[str, float]] = {}  # code -> {qty, entry}
        self.cost_bps = float(cost_bps)
        self.slip_bps = float(slip_bps)
        self.trades: List[Dict[str, Any]] = []

    def _cost(self, gross: float) -> float:
        return gross * (self.cost_bps / 10000.0)

    def _buy_px(self, px: float) -> float:
        return px * (1.0 + self.slip_bps / 10000.0)

    def _sell_px(self, px: float) -> float:
        return px * (1.0 - self.slip_bps / 10000.0)

    def buy(self, dt: datetime, code: str, px: float, pos_pct: float):
        if code in self.positions:
            return
        if px <= 0 or pos_pct <= 1e-9:
            return
        exec_px = self._buy_px(px)
        budget = self.cash * float(pos_pct)
        qty = 0.0 if exec_px <= 0 else (budget / exec_px)
        gross = qty * exec_px
        fee = self._cost(gross)
        out = gross + fee
        if qty > 0 and out <= self.cash:
            self.cash -= out
            self.positions[code] = {"qty": qty, "entry": exec_px}
            self.trades.append({
                "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "etf_code": code,
                "action": "buy",
                "price": exec_px,
                "quantity": qty,
                "value": gross,
                "capital_after": self.cash,
                "reasoning": "backtest buy",
            })

    def sell(self, dt: datetime, code: str, px: float, ratio: float = 1.0):
        if code not in self.positions:
            return
        qty_all = self.positions[code]["qty"]
        if qty_all <= 0:
            return
        qty = qty_all * float(ratio)
        exec_px = self._sell_px(px)
        gross = qty * exec_px
        fee = self._cost(gross)
        net_in = gross - fee
        self.cash += net_in
        self.trades.append({
            "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "etf_code": code,
            "action": "sell",
            "price": exec_px,
            "quantity": qty,
            "value": gross,
            "capital_after": self.cash,
            "reasoning": "backtest sell",
        })
        remain = qty_all - qty
        if remain <= 1e-9:
            del self.positions[code]
        else:
            self.positions[code]["qty"] = remain

    def equity(self, prices: Dict[str, float]) -> float:
        val = self.cash
        for c, pos in self.positions.items():
            px = float(prices.get(c, 0.0) or 0.0)
            val += pos["qty"] * (px if px > 0 else 0.0)
        return val


def _date_range_union(series_map: Dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp) -> List[pd.Timestamp]:
    idx: List[pd.Timestamp] = []
    for df in series_map.values():
        s = df[(df["date"] >= start) & (df["date"] <= end)]["date"].tolist()
        idx.extend(s)
    uniq = sorted(set(idx))
    return uniq


def run_backtest(etf_list: List[str], start: str, end: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Run a pure in-memory backtest and return dict for web consumption."""
    # Params & env
    if params is None:
        params = {}
    try:
        init_cap = float(os.getenv("INITIAL_CAPITAL", "100000"))
    except Exception:
        init_cap = 100000.0
    cost_bps = float(os.getenv("COST_BPS", "5"))
    slip_bps = float(os.getenv("SLIPPAGE_BPS", "2"))
    base_pos = float(os.getenv("BASE_POSITION_PCT", "0.15"))
    max_pos = float(os.getenv("MAX_POSITION_PCT", "0.20"))

    # Rule params
    rule_params = {
        "mode": os.getenv("STRATEGY_MODE", "AGGRESSIVE"),
        "breakout_n": int(os.getenv("BREAKOUT_N", str(params.get("breakout_n", 60)))),
        "rsi_n": int(os.getenv("RSI_N", str(params.get("rsi_n", 6)))),
        "rsi_low": int(os.getenv("RSI_LOW", "8")),
        "rsi_high": int(os.getenv("RSI_HIGH", "92")),
        "kdj_low": int(os.getenv("KDJ_LOW", "20")),
    }

    # Load series
    codes = [c.strip() for c in etf_list if c and c.strip()]
    series_map: Dict[str, pd.DataFrame] = {}
    for c in codes:
        df = _read_series(c)
        if not df.empty:
            series_map[c] = df
    if not series_map:
        return {"equity": {"dates": [], "values": []}, "kpis": {}, "trades": [], "daily_trades": []}

    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    dates = _date_range_union(series_map, start_dt, end_dt)
    if not dates:
        return {"equity": {"dates": [], "values": []}, "kpis": {}, "trades": [], "daily_trades": []}

    # Executor
    exe = _BTExecutor(initial_capital=init_cap, cost_bps=cost_bps, slip_bps=slip_bps)

    eq_dates: List[str] = []
    eq_vals: List[float] = []
    daily_counts: List[Dict[str, Any]] = []

    for d in dates:
        # build current price map for valuation
        cur_px: Dict[str, float] = {}
        buy_cnt = 0; sell_cnt = 0
        for code, df in series_map.items():
            # window up to d
            sub = df[df["date"] <= d]
            if sub.empty:
                continue
            cur_px[code] = float(sub.iloc[-1]["close"])
            # require at least 60 bars
            win = sub.tail(200)
            if len(win) < 60:
                continue
            # rule decision
            rd = get_rule_decision(pd.DataFrame({
                "收盘": win["close"].values,
                "日期": win["date"].values,
            }), rule_params, etf_code=code)
            decision = (rd or {}).get("decision", "hold").lower()
            # Simple execution policy: buy if not holding; sell if holding
            if decision == "buy" and code not in exe.positions:
                exe.buy(d.to_pydatetime(), code, cur_px[code], pos_pct=min(base_pos, max_pos))
                buy_cnt += 1
            elif decision == "sell" and code in exe.positions:
                exe.sell(d.to_pydatetime(), code, cur_px[code], ratio=1.0)
                sell_cnt += 1
        eq_dates.append(d.strftime("%Y-%m-%d"))
        eq_vals.append(exe.equity(cur_px))
        daily_counts.append({"date": d.strftime("%Y-%m-%d"), "buy": buy_cnt, "sell": sell_cnt})

    # KPIs
    equity = np.array(eq_vals, dtype=float)
    if equity.size >= 2:
        total_ret = (equity[-1] - equity[0]) / equity[0]
        days = max((pd.to_datetime(eq_dates[-1]) - pd.to_datetime(eq_dates[0])).days, 1)
        ann = total_ret * (365.0 / days)
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / peak
        mdd = float(dd.min())
    else:
        total_ret = 0.0; ann = 0.0; mdd = 0.0

    trades_df = pd.DataFrame(exe.trades)
    buy_count = int((trades_df["action"].str.lower() == "buy").sum()) if not trades_df.empty else 0
    sell_count = int((trades_df["action"].str.lower() == "sell").sum()) if not trades_df.empty else 0
    win_rate = 0.0
    if not trades_df.empty:
        t = trades_df.copy()
        t["profit"] = t.apply(lambda r: float(r["value"]) if str(r["action"]).lower()=="sell" else -float(r["value"]), axis=1)
        sells = t[t["action"].str.lower()=="sell"]
        if not sells.empty:
            win_rate = 100.0 * float((sells["profit"] > 0).mean())

    kpis = {
        "total_trades": int(buy_count + sell_count),
        "buy_count": int(buy_count),
        "sell_count": int(sell_count),
        "win_rate": float(win_rate),
        "total_return": float(total_ret*100.0),
        "annualized_return": float(ann*100.0),
        "max_drawdown": float(mdd*100.0),
    }

    return {
        "equity": {"dates": eq_dates, "values": [float(v) for v in eq_vals]},
        "kpis": kpis,
        "trades": exe.trades,
        "daily_trades": daily_counts,
    }

