#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_cash_holdings_20251217_20251223.py

核对“虚高修正”后的数据闭环：
- 对指定日期区间（默认 2025-12-17 ~ 2025-12-23）
- 计算：cash(asof date) + holdings_value(positions asof date, valued at that date close)
- 同时对比：daily_equity 表中的 equity（若存在）

数据来源（与你项目真实结构一致）：
- cash：trade_history.db / trades.capital_after（<= date 23:59:59 的最后一条）
- positions：trade_history.db / trades 流水重建（<= date 23:59:59）
- prices：etf_data.db / etf_<code>（<= date 的最近收盘价）

运行：
  cd "D:\Quantitative Trading\ai-etf-trader"
  python audit_cash_holdings_20251217_20251223.py

"""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, Optional, List, Tuple

TRADE_DB = os.path.join('data', 'trade_history.db')
ETF_DB = os.path.join('data', 'etf_data.db')

START = '2025-12-17'
END = '2025-12-23'


def _cash_asof(con: sqlite3.Connection, day: str) -> Optional[float]:
    cur = con.cursor()
    cur.execute(
        "SELECT capital_after FROM trades WHERE datetime(date) <= datetime(?) ORDER BY datetime(date) DESC LIMIT 1",
        (day + ' 23:59:59',),
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def _positions_asof(con: sqlite3.Connection, day: str) -> Dict[str, float]:
    cur = con.cursor()
    cur.execute(
        "SELECT etf_code, action, quantity FROM trades WHERE datetime(date) <= datetime(?) ORDER BY datetime(date)",
        (day + ' 23:59:59',),
    )
    pos: Dict[str, float] = {}
    for code, act, qty in cur.fetchall():
        c = str(code).strip()
        if not c:
            continue
        a = str(act).lower().strip()
        try:
            q = float(qty or 0)
        except Exception:
            q = 0.0
        if a == 'sell':
            q = -q
        pos[c] = pos.get(c, 0.0) + q
    pos = {c: q for c, q in pos.items() if q > 1e-9}
    return pos


def _close_asof(code: str, day: str) -> Optional[float]:
    if not os.path.exists(ETF_DB):
        return None
    con = sqlite3.connect(ETF_DB)
    try:
        try:
            row = con.execute(
                f"SELECT 收盘 FROM etf_{code} WHERE 日期 <= ? ORDER BY 日期 DESC LIMIT 1",
                (day,),
            ).fetchone()
            if row and row[0] is not None:
                px = float(row[0])
                return px if px > 0 else None
        except Exception:
            pass
        try:
            row = con.execute(
                f"SELECT close FROM etf_{code} WHERE date <= ? ORDER BY date DESC LIMIT 1",
                (day,),
            ).fetchone()
            if row and row[0] is not None:
                px = float(row[0])
                return px if px > 0 else None
        except Exception:
            pass
        return None
    finally:
        con.close()


def _daily_equity(con: sqlite3.Connection, day: str) -> Optional[float]:
    cur = con.cursor()
    cur.execute('SELECT equity FROM daily_equity WHERE date=?', (day,))
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def _date_range(start: str, end: str) -> List[str]:
    import pandas as pd
    ds = pd.date_range(start=start, end=end, freq='D')
    return [d.strftime('%Y-%m-%d') for d in ds]


def main():
    if not os.path.exists(TRADE_DB):
        raise SystemExit('missing data/trade_history.db')
    if not os.path.exists(ETF_DB):
        print('[WARN] missing data/etf_data.db (prices will be None)')

    con = sqlite3.connect(TRADE_DB)
    try:
        days = _date_range(START, END)
        print('date,cash,holdings,total(c+h),daily_equity,delta(total-daily_equity),missing_px')
        for day in days:
            cash = _cash_asof(con, day)
            if cash is None:
                cash = 0.0
            pos = _positions_asof(con, day)
            hv = 0.0
            missing = []
            for code, qty in pos.items():
                px = _close_asof(code, day)
                if px is None:
                    missing.append(code)
                    continue
                hv += qty * px
            total = cash + hv
            deq = _daily_equity(con, day)
            delta = (total - deq) if deq is not None else None
            print(f"{day},{cash:.2f},{hv:.2f},{total:.2f},{'' if deq is None else f'{deq:.2f}'},{'' if delta is None else f'{delta:.2f}'},{'|'.join(missing)}")
    finally:
        con.close()


if __name__ == '__main__':
    main()

