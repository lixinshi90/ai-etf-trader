#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cancel_today_and_fill_20251224.py

按你最新口径修复：
1) 取消 2025-12-25 的 daily_equity（并删除 2025-12-25 当天 trades，如存在）
2) 补写 2025-12-24 的 daily_equity：
   - 持仓数量使用“截至 2025-12-23 的持仓”（由 trades 流水重建）
   - 用 2025-12-24 收盘价对这批持仓重新估值，得到 holdings_value_1224
   - 现金采用 2025-12-23 的现金（trades.capital_after 截至 12/23 最后一笔；若无则取 initial_capital）
   - 总资产_1224 = 现金_1223 + holdings_value_1224

重要：
- 12/24 总资产不强行等于 99795.48（因为收盘价变化会带来合理波动）
- 仅保证：持仓数量口径一致（12/23 的持仓），估值价格口径一致（12/24 收盘价），现金口径一致（12/23 现金）

运行：
  cd "D:\Quantitative Trading\ai-etf-trader"
  python cancel_today_and_fill_20251224.py

会自动备份 data/trade_history.db -> data/trade_history.db.bak_before_fill_20251224
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from typing import Dict, Optional

TRADE_DB = os.path.join('data', 'trade_history.db')
ETF_DB = os.path.join('data', 'etf_data.db')
BACKUP_DB = os.path.join('data', 'trade_history.db.bak_before_fill_20251224')

DAY_TODAY = '2025-12-25'
DAY_1224 = '2025-12-24'
DAY_1223 = '2025-12-23'


def backup():
    if not os.path.exists(TRADE_DB):
        raise SystemExit(f'missing {TRADE_DB}')
    shutil.copy2(TRADE_DB, BACKUP_DB)
    print('[fix] backed up:', BACKUP_DB)


def _read_close_asof(code: str, asof_date: str) -> Optional[float]:
    if not os.path.exists(ETF_DB):
        return None
    con = sqlite3.connect(ETF_DB)
    try:
        # Chinese schema
        try:
            row = con.execute(
                f"SELECT 收盘 FROM etf_{code} WHERE 日期 <= ? ORDER BY 日期 DESC LIMIT 1",
                (asof_date,),
            ).fetchone()
            if row and row[0] is not None:
                px = float(row[0])
                return px if px > 0 else None
        except Exception:
            pass
        # English schema
        try:
            row = con.execute(
                f"SELECT close FROM etf_{code} WHERE date <= ? ORDER BY date DESC LIMIT 1",
                (asof_date,),
            ).fetchone()
            if row and row[0] is not None:
                px = float(row[0])
                return px if px > 0 else None
        except Exception:
            pass
        return None
    finally:
        con.close()


def _rebuild_positions(asof_date: str) -> Dict[str, float]:
    """持仓数量按 trades 流水重建（截至 asof_date 23:59:59）。"""
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


def _delete_day(day: str):
    con = sqlite3.connect(TRADE_DB)
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM daily_equity WHERE date=?", (day,))
        de = cur.rowcount
        cur.execute("DELETE FROM trades WHERE date LIKE ?", (day + '%',))
        tr = cur.rowcount
        con.commit()
        print(f'[fix] deleted {day}: daily_equity rows={de}, trades rows={tr}')
    finally:
        con.close()


def _upsert_equity(day: str, equity: float):
    con = sqlite3.connect(TRADE_DB)
    try:
        cur = con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")
        cur.execute(
            "INSERT INTO daily_equity(date,equity) VALUES(?,?) ON CONFLICT(date) DO UPDATE SET equity=excluded.equity",
            (day, float(equity)),
        )
        con.commit()
        print(f'[fix] upsert daily_equity {day} = {equity:.2f}')
    finally:
        con.close()


def main():
    backup()

    # 1) 取消 12/25（快照+当日交易，如果有）
    _delete_day(DAY_TODAY)

    # 2) 计算 12/24 的持仓市值：使用 12/23 的持仓数量，按 12/24 收盘价估值
    pos_1223 = _rebuild_positions(DAY_1223)

    hv_1224 = 0.0
    missing = []
    for code, qty in pos_1223.items():
        px = _read_close_asof(code, DAY_1224)
        if px is None:
            missing.append(code)
            continue
        hv_1224 += float(qty) * float(px)

    if missing:
        print('[fix] WARNING missing prices for 2025-12-24 codes=', missing)

    cash_1223 = _cash_asof(DAY_1223)
    if cash_1223 is None:
        cash_1223 = float(os.getenv('INITIAL_CAPITAL', '100000'))
        print(f'[fix] WARNING no cash snapshot <= {DAY_1223}, fallback initial_capital={cash_1223:.2f}')

    total_1224 = float(cash_1223) + float(hv_1224)

    print(f'[fix] positions(asof {DAY_1223}) count={len(pos_1223)}')
    print(f'[fix] cash(asof {DAY_1223})={cash_1223:.2f}')
    print(f'[fix] holdings@{DAY_1224}={hv_1224:.2f}')
    print(f'[fix] total@{DAY_1224}={total_1224:.2f}')

    # 3) 写入 12/24 快照
    _upsert_equity(DAY_1224, total_1224)

    # 打印最近 10 条
    con = sqlite3.connect(TRADE_DB)
    try:
        cur = con.cursor()
        cur.execute('SELECT date,equity FROM daily_equity ORDER BY date DESC LIMIT 10')
        print('[fix] latest daily_equity:')
        for r in cur.fetchall():
            print(' ', r)
    finally:
        con.close()


if __name__ == '__main__':
    main()
