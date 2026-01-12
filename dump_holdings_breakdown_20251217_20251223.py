#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dump_holdings_breakdown_20251217_20251223.py

按天输出持仓明细（满足你要的“现金+持仓”逐日核对）：
- 日期范围：2025-12-17 ~ 2025-12-23（可在脚本顶部改 START/END）
- 每天输出一个 CSV：out/holdings_breakdown_<date>.csv

每个 CSV 包含：
- code
- qty_asof            截至当日 23:59:59 的净持仓数量（由 trades 流水重建）
- close_asof          截至当日的最近收盘价（从 etf_data.db 的 etf_<code> 取 <= date 的最近一条）
- value               qty * close
- flags               异常标记（缺价/<=0）

同时在控制台打印：
- cash_asof
- holdings_total
- total(cash+holdings)
- daily_equity(若存在)
- delta
- missing_px

运行：
  cd "D:\Quantitative Trading\ai-etf-trader"
  python dump_holdings_breakdown_20251217_20251223.py

"""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, Optional, List

import pandas as pd

TRADE_DB = os.path.join('data', 'trade_history.db')
ETF_DB = os.path.join('data', 'etf_data.db')
OUT_DIR = os.path.join('out')

START = '2025-12-17'
END = '2025-12-23'


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


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


def _daily_equity(con: sqlite3.Connection, day: str) -> Optional[float]:
    cur = con.cursor()
    cur.execute('SELECT equity FROM daily_equity WHERE date=?', (day,))
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def _close_asof(code: str, day: str) -> Optional[float]:
    if not os.path.exists(ETF_DB):
        return None
    con = sqlite3.connect(ETF_DB)
    try:
        # Chinese
        try:
            row = con.execute(
                f"SELECT 收盘, 日期 FROM etf_{code} WHERE 日期 <= ? ORDER BY 日期 DESC LIMIT 1",
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
                f"SELECT close, date FROM etf_{code} WHERE date <= ? ORDER BY date DESC LIMIT 1",
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


def main():
    if not os.path.exists(TRADE_DB):
        raise SystemExit('missing data/trade_history.db')
    if not os.path.exists(ETF_DB):
        print('[WARN] missing data/etf_data.db, close prices will be None')

    _ensure_dir(OUT_DIR)

    days = pd.date_range(start=START, end=END, freq='D')

    tcon = sqlite3.connect(TRADE_DB)
    try:
        for d in days:
            day = d.strftime('%Y-%m-%d')
            cash = _cash_asof(tcon, day)
            if cash is None:
                cash = 0.0
            pos = _positions_asof(tcon, day)

            rows: List[dict] = []
            hv = 0.0
            missing = []
            for code, qty in sorted(pos.items()):
                px = _close_asof(code, day)
                if px is None:
                    missing.append(code)
                    rows.append({
                        'code': code,
                        'qty_asof': qty,
                        'close_asof': None,
                        'value': None,
                        'flags': 'MISSING_PX',
                    })
                    continue
                val = qty * px
                hv += val
                rows.append({
                    'code': code,
                    'qty_asof': qty,
                    'close_asof': px,
                    'value': val,
                    'flags': '',
                })

            total = cash + hv
            deq = _daily_equity(tcon, day)
            delta = (total - deq) if deq is not None else None

            # 输出 CSV
            out_fp = os.path.join(OUT_DIR, f'holdings_breakdown_{day}.csv')
            df_out = pd.DataFrame(rows)
            if not df_out.empty and 'value' in df_out.columns:
                df_out = df_out.sort_values('value', ascending=False, na_position='last')
            df_out.to_csv(out_fp, index=False, encoding='utf-8-sig')

            print(f'\n=== {day} ===')
            print(f'cash={cash:.2f} holdings={hv:.2f} total={total:.2f} daily_equity={("" if deq is None else f"{deq:.2f}")} delta={("" if delta is None else f"{delta:.2f}")} missing_px={missing}')
            print(f'-> wrote {out_fp} (rows={len(rows)})')

    finally:
        tcon.close()


if __name__ == '__main__':
    main()

