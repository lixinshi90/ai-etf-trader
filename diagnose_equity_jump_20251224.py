#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diagnose_equity_jump_20251224.py

目的：定位 2025-12-24 净值相对 2025-12-23 跳变过大（约 10%）的原因。
优先假设原因来自 etf_data.db 的价格录入异常；同时检查 trades 持仓数量是否异常。

输出：
1) 截至 2025-12-23 的持仓数量（从 trade_history.db 的 trades 流水重建）
2) 分别用 2025-12-23 和 2025-12-24 的收盘价估值持仓市值
3) 每个标的的“价格涨跌”“市值贡献”“对总资产贡献”
4) 标记可疑：
   - 单日价格涨跌幅 > 5%
   - 或价格<=0/缺失
   - 或单标的对总资产贡献过大（默认>3%）

运行：
  cd "D:\Quantitative Trading\ai-etf-trader"
  python diagnose_equity_jump_20251224.py

"""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, Optional, Tuple, List

TRADE_DB = os.path.join('data', 'trade_history.db')
ETF_DB = os.path.join('data', 'etf_data.db')

ASOF = '2025-12-23'     # 持仓数量截至日
D0 = '2025-12-23'       # 基准价格日
D1 = '2025-12-24'       # 对比价格日

PRICE_JUMP_PCT = 5.0    # 单日价格涨跌幅阈值
CONTRIB_PCT = 3.0       # 单标的对总资产贡献阈值


def _rebuild_positions(asof_date: str) -> Dict[str, float]:
    con = sqlite3.connect(TRADE_DB)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT etf_code, action, quantity FROM trades WHERE datetime(date) <= datetime(?) ORDER BY datetime(date)",
            (asof_date + ' 23:59:59',),
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
    finally:
        con.close()


def _cash_asof(asof_date: str) -> Optional[float]:
    con = sqlite3.connect(TRADE_DB)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT capital_after FROM trades WHERE datetime(date) <= datetime(?) ORDER BY datetime(date) DESC LIMIT 1",
            (asof_date + ' 23:59:59',),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return float(row[0])
    finally:
        con.close()


def _read_close_on(code: str, date: str) -> Optional[float]:
    if not os.path.exists(ETF_DB):
        return None
    con = sqlite3.connect(ETF_DB)
    try:
        # 优先“等于当日”，否则用 <= 当日 最近一条
        # Chinese
        try:
            row = con.execute(
                f"SELECT 收盘 FROM etf_{code} WHERE 日期 <= ? ORDER BY 日期 DESC LIMIT 1",
                (date,),
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
                (date,),
            ).fetchone()
            if row and row[0] is not None:
                px = float(row[0])
                return px if px > 0 else None
        except Exception:
            pass
        return None
    finally:
        con.close()


def main():
    if not os.path.exists(TRADE_DB):
        raise SystemExit('missing trade_history.db')
    if not os.path.exists(ETF_DB):
        raise SystemExit('missing etf_data.db')

    pos = _rebuild_positions(ASOF)
    cash = _cash_asof(ASOF)
    if cash is None:
        cash = float(os.getenv('INITIAL_CAPITAL', '100000'))

    rows: List[dict] = []
    hv0 = 0.0
    hv1 = 0.0
    missing = []

    for code, qty in sorted(pos.items()):
        p0 = _read_close_on(code, D0)
        p1 = _read_close_on(code, D1)
        if p0 is None or p1 is None:
            missing.append(code)
            continue
        v0 = qty * p0
        v1 = qty * p1
        hv0 += v0
        hv1 += v1
        chg_pct = (p1 / p0 - 1.0) * 100.0 if p0 > 0 else 0.0
        rows.append({
            'code': code,
            'qty': qty,
            'p0': p0,
            'p1': p1,
            'p_chg_pct': chg_pct,
            'v0': v0,
            'v1': v1,
            'dv': v1 - v0,
        })

    total0 = cash + hv0
    total1 = cash + hv1
    total_chg_pct = (total1 / total0 - 1.0) * 100.0 if total0 > 0 else 0.0

    print(f'=== Holdings as of {ASOF} valued on {D0} vs {D1} ===')
    print(f'cash(asof {ASOF}) = {cash:.2f}')
    print(f'holdings@{D0} = {hv0:.2f}')
    print(f'holdings@{D1} = {hv1:.2f}')
    print(f'total@{D0} = {total0:.2f}')
    print(f'total@{D1} = {total1:.2f}')
    print(f'total change = {total_chg_pct:.2f}%')

    if missing:
        print('\n[WARN] missing price codes:', missing)

    print('\nPer-code breakdown:')
    # sort by abs dv
    rows_sorted = sorted(rows, key=lambda r: abs(r['dv']), reverse=True)
    for r in rows_sorted:
        contrib_pct = (r['dv'] / total0 * 100.0) if total0 > 0 else 0.0
        flags = []
        if abs(r['p_chg_pct']) > PRICE_JUMP_PCT:
            flags.append(f'PRICE_JUMP>{PRICE_JUMP_PCT:.0f}%')
        if abs(contrib_pct) > CONTRIB_PCT:
            flags.append(f'CONTRIB>{CONTRIB_PCT:.0f}%')
        flag_str = (' | ' + ','.join(flags)) if flags else ''
        print(
            f"{r['code']} qty={r['qty']:.4f} p0={r['p0']:.4f} p1={r['p1']:.4f} "
            f"pchg={r['p_chg_pct']:+.2f}% v0={r['v0']:.2f} v1={r['v1']:.2f} dv={r['dv']:+.2f} "
            f"contrib={contrib_pct:+.2f}%{flag_str}"
        )

    print('\nIf you see extreme p1 or pchg%, it likely indicates etf_data.db bad price input.')


if __name__ == '__main__':
    main()

