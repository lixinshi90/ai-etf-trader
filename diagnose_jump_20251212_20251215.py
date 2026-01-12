#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diagnose_jump_20251212_20251215.py

诊断 corrected_daily_equity.csv 中 2025-12-12 -> 2025-12-15 的异常跳变。

做法：
- 用 trade_history.db 的 trades 流水重建截至指定日期的现金(capital_after)与持仓数量
- 用 etf_data.db 的收盘价对持仓估值
- 输出两天的现金、持仓明细、总资产，并给出差异来源

运行：
  cd "D:\\Quantitative Trading\\ai-etf-trader"
  python diagnose_jump_20251212_20251215.py

"""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, Optional, List, Tuple

TRADE_DB = os.path.join('data', 'trade_history.db')
ETF_DB = os.path.join('data', 'etf_data.db')

D0 = '2025-12-12'
D1 = '2025-12-15'


def _cash_asof(con: sqlite3.Connection, day: str) -> Optional[float]:
    cur = con.cursor()
    cur.execute(
        "SELECT date, capital_after FROM trades WHERE datetime(date) <= datetime(?) ORDER BY datetime(date) DESC LIMIT 1",
        (day + ' 23:59:59',),
    )
    row = cur.fetchone()
    if not row or row[1] is None:
        return None
    return float(row[1])


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
        # Chinese
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
        # English
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


def snapshot(day: str) -> Tuple[float, float, float, List[dict], List[str]]:
    tcon = sqlite3.connect(TRADE_DB)
    try:
        cash = _cash_asof(tcon, day)
        if cash is None:
            cash = 0.0
        pos = _positions_asof(tcon, day)
    finally:
        tcon.close()

    hv = 0.0
    rows: List[dict] = []
    missing: List[str] = []
    for code, qty in sorted(pos.items()):
        px = _close_asof(code, day)
        if px is None:
            missing.append(code)
            continue
        val = qty * px
        hv += val
        rows.append({'code': code, 'qty': qty, 'px': px, 'value': val})

    total = cash + hv
    return cash, hv, total, rows, missing


def main():
    if not os.path.exists(TRADE_DB):
        raise SystemExit('missing data/trade_history.db')
    if not os.path.exists(ETF_DB):
        raise SystemExit('missing data/etf_data.db')

    c0, h0, t0, r0, m0 = snapshot(D0)
    c1, h1, t1, r1, m1 = snapshot(D1)

    print(f'=== Snapshot {D0} ===')
    print(f'cash={c0:.2f} holdings={h0:.2f} total={t0:.2f} missing_px={m0}')
    for r in sorted(r0, key=lambda x: x['value'], reverse=True):
        print(f"  {r['code']} qty={r['qty']:.4f} px={r['px']:.4f} val={r['value']:.2f}")

    print(f'\n=== Snapshot {D1} ===')
    print(f'cash={c1:.2f} holdings={h1:.2f} total={t1:.2f} missing_px={m1}')
    for r in sorted(r1, key=lambda x: x['value'], reverse=True):
        print(f"  {r['code']} qty={r['qty']:.4f} px={r['px']:.4f} val={r['value']:.2f}")

    print('\n=== Diff (D1 - D0) ===')
    print(f'cash diff = {c1-c0:+.2f}')
    print(f'holdings diff = {h1-h0:+.2f}')
    print(f'total diff = {t1-t0:+.2f} ({(t1/t0-1)*100 if t0>0 else 0:.2f}%)')

    # identify which codes contribute most to holdings change
    v0 = {r['code']: r['value'] for r in r0}
    v1 = {r['code']: r['value'] for r in r1}
    all_codes = sorted(set(v0.keys()) | set(v1.keys()))
    contrib = []
    for code in all_codes:
        dv = v1.get(code, 0.0) - v0.get(code, 0.0)
        contrib.append((abs(dv), dv, code, v0.get(code, 0.0), v1.get(code, 0.0)))
    contrib.sort(reverse=True)
    print('\nTop holdings value changes:')
    for _, dv, code, a, b in contrib[:20]:
        print(f'  {code}: {a:.2f} -> {b:.2f}  dv={dv:+.2f}')


if __name__ == '__main__':
    main()

