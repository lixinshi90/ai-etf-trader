#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按“当日持仓数量 × 当日收盘价 + 现金”重估给定日期的净值，并写回 data/trade_history.db.daily_equity。
- 现金：取该日（含当日）最后一笔交易的 capital_after；若无任何交易，则取 config.yaml.strategy.initial_capital
- 持仓：累加该日（含当日）之前所有交易（buy 加、sell 减）得到数量；用 etf_data.db 中 <= 当日 的最近收盘价估值

用法：
  uv run python -m tools.revalue_equity --dates 2025-11-30,2025-12-01
  uv run python -m tools.revalue_equity --dates 2025-12-01 --verbose
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
DB_TRADES = ROOT / 'data' / 'trade_history.db'
DB_ETF = ROOT / 'data' / 'etf_data.db'
CFG = ROOT / 'config.yaml'


def _initial_capital() -> float:
    init = 100000.0
    if yaml is None or not CFG.exists():
        return init
    try:
        with CFG.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        return float((data.get('strategy') or {}).get('initial_capital', init))
    except Exception:
        return init


def _get_etf_price_asof(code: str, asof: str, conn_etf: sqlite3.Connection) -> float:
    # 兼容中文/英文列名，按日期<=asof 最近一条
    for date_col in ('日期', 'date', 'Date'):
        for close_col in ('收盘', '收盘价', 'close', 'Close'):
            try:
                q = f"SELECT {close_col} AS px, {date_col} AS dt FROM etf_{code} WHERE {date_col} <= ? ORDER BY {date_col} DESC LIMIT 1"
                df = pd.read_sql_query(q, conn_etf, params=(asof,))
                if not df.empty and pd.notna(df.loc[0, 'px']):
                    return float(df.loc[0, 'px'])
            except Exception:
                continue
    return 0.0


def _load_trades_until(asof: str, conn_tr: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT date, etf_code, action, price, quantity, capital_after FROM trades ORDER BY datetime(date)",
        conn_tr,
    )
    if df.empty:
        return df
    # 保留 <= asof 的交易
    df['dt'] = pd.to_datetime(df['date'], errors='coerce')
    asof_ts = pd.to_datetime(asof)
    df = df[df['dt'] <= asof_ts]
    return df


def _positions_asof(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {}
    rows = []
    for _, r in df.iterrows():
        code = str(r.get('etf_code') or '').strip()
        if not code:
            continue
        act = str(r.get('action') or '').lower()
        qty = float(r.get('quantity') or 0.0)
        if act == 'sell':
            qty = -qty
        rows.append((code, qty))
    if not rows:
        return {}
    pos: Dict[str, float] = {}
    for code, dq in rows:
        pos[code] = pos.get(code, 0.0) + float(dq)
    # 只返回正仓位
    return {k: v for k, v in pos.items() if v > 1e-9}


def _cash_asof(df: pd.DataFrame) -> float:
    if df.empty:
        return _initial_capital()
    # 当日最后一笔交易后的现金
    last = df.iloc[-1]
    try:
        return float(last.get('capital_after') or 0.0)
    except Exception:
        return _initial_capital()


def revalue_dates(dates: List[str], verbose: bool = False) -> None:
    if not DB_TRADES.exists():
        raise SystemExit(f"trades db not found: {DB_TRADES}")
    if not DB_ETF.exists():
        raise SystemExit(f"etf db not found: {DB_ETF}")

    conn_tr = sqlite3.connect(str(DB_TRADES))
    conn_etf = sqlite3.connect(str(DB_ETF))
    try:
        for d in dates:
            # 1) 取截至当日的交易
            tdf = _load_trades_until(d, conn_tr)
            # 2) 现金与持仓
            cash = _cash_asof(tdf)
            pos = _positions_asof(tdf)
            # 3) 估值
            holdings_value = 0.0
            detail = []
            for code, qty in pos.items():
                px = _get_etf_price_asof(code, d, conn_etf)
                val = qty * (px if px > 0 else 0.0)
                holdings_value += val
                if verbose:
                    detail.append((code, qty, px, val))
            total = cash + holdings_value
            # 4) 写回 daily_equity（UPSERT）
            conn_tr.execute(
                "CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)"
            )
            conn_tr.execute(
                "INSERT INTO daily_equity(date,equity) VALUES(?,?) ON CONFLICT(date) DO UPDATE SET equity=excluded.equity",
                (d, float(total)),
            )
            conn_tr.commit()
            if verbose:
                print(f"[revalue] {d}: cash={cash:.2f} holdings={holdings_value:.2f} total={total:.2f}")
                for code, qty, px, val in detail:
                    print(f"  - {code} qty={qty:.4f} px={px:.4f} val={val:.2f}")
    finally:
        conn_tr.close()
        conn_etf.close()


def main() -> int:
    ap = argparse.ArgumentParser(description='重估指定日期的净值（当日持仓×收盘价 + 现金）')
    ap.add_argument('--dates', type=str, required=True, help='逗号分隔的日期列表，如 2025-11-30,2025-12-01')
    ap.add_argument('--verbose', action='store_true', help='打印估值明细')
    args = ap.parse_args()

    dates = [s.strip() for s in args.dates.split(',') if s.strip()]
    if not dates:
        print('[error] 未提供有效日期')
        return 1

    revalue_dates(dates, verbose=args.verbose)
    print('=== 重估完成 ===')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

