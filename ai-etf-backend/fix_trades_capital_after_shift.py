#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_trades_capital_after_shift.py

你选择“以 99795.48 为真”，因此需要把 trade_history.db 的 trades.capital_after 现金链
整体平移，使得“2025-12-23 当天最后一笔交易的 capital_after” 与 daily_equity(2025-12-23)
一致。

注意：这是一种“历史修账（平移现金链）”的工程化处理：
- 不改变每笔交易的 price/quantity/value（保持成交记录）
- 只调整 capital_after（账户现金快照）
- 目的：让 restore_state_from_db() 恢复出的现金与修正后的净值曲线一致，
  从而避免后续 daily_once 计算资产时出现系统性偏高/偏低。

它会：
1) 备份数据库 -> data/trade_history.db.bak_capital_shift
2) 计算 delta = daily_equity[target_date] - last_trade_capital_after(target_date)
3) 对 trades 表中 date >= cutoff_date 的记录：capital_after += delta
   （默认从 target_date 当天开始平移；你可改 CUTOFF_DATE）
4) 打印校验信息

运行（项目根目录）：
  python fix_trades_capital_after_shift.py

"""

from __future__ import annotations

import os
import shutil
import sqlite3

DB_PATH = os.path.join('data', 'trade_history.db')
BACKUP_PATH = os.path.join('data', 'trade_history.db.bak_capital_shift')

# 以该日为“锚点”：daily_equity 的净值作为真值
TARGET_DATE = '2025-12-23'
# 从哪天开始平移 capital_after（建议与 TARGET_DATE 同日，避免破坏更早历史）
CUTOFF_DATE = '2025-12-23'


def backup_db():
    if not os.path.exists(DB_PATH):
        raise SystemExit(f'找不到数据库: {DB_PATH}')
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f'[capital_shift] 已备份数据库: {BACKUP_PATH}')


def main():
    backup_db()

    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()

        # 取目标日净值
        cur.execute('SELECT equity FROM daily_equity WHERE date=?', (TARGET_DATE,))
        r = cur.fetchone()
        if not r:
            raise SystemExit(f'[capital_shift] daily_equity 中不存在 {TARGET_DATE}')
        target_equity = float(r[0])

        # 取目标日最后一笔交易的 capital_after
        cur.execute(
            "SELECT date, capital_after FROM trades WHERE date LIKE ? ORDER BY datetime(date) DESC LIMIT 1",
            (TARGET_DATE + '%',),
        )
        r2 = cur.fetchone()
        if not r2:
            raise SystemExit(f'[capital_shift] trades 中不存在 {TARGET_DATE} 的交易记录，无法锚定')
        last_trade_ts = str(r2[0])
        last_capital = float(r2[1])

        delta = target_equity - last_capital
        print(f'[capital_shift] target_equity({TARGET_DATE}) = {target_equity:.6f}')
        print(f'[capital_shift] last_trade_capital_after({last_trade_ts}) = {last_capital:.6f}')
        print(f'[capital_shift] delta = {delta:.6f}')

        # 平移 cutoff 之后所有记录（含 cutoff 当日）
        cutoff_ts = CUTOFF_DATE + ' 00:00:00'
        cur.execute('SELECT count(1) FROM trades WHERE datetime(date) >= datetime(?)', (cutoff_ts,))
        n = int(cur.fetchone()[0])
        print(f'[capital_shift] trades rows to update (>= {cutoff_ts}): {n}')

        cur.execute(
            'UPDATE trades SET capital_after = capital_after + ? WHERE datetime(date) >= datetime(?)',
            (delta, cutoff_ts),
        )
        print(f'[capital_shift] updated rows: {cur.rowcount}')

        con.commit()

        # 校验：目标日最后一笔 capital_after 是否对齐
        cur.execute(
            "SELECT date, capital_after FROM trades WHERE date LIKE ? ORDER BY datetime(date) DESC LIMIT 1",
            (TARGET_DATE + '%',),
        )
        r3 = cur.fetchone()
        print(f'[capital_shift] after shift last_trade_capital_after: {r3}')

        # 校验：最新一笔 trade 的 capital_after
        cur.execute('SELECT date, capital_after FROM trades ORDER BY datetime(date) DESC LIMIT 1')
        print(f'[capital_shift] latest trade capital_after: {cur.fetchone()}')

    finally:
        con.close()


if __name__ == '__main__':
    main()

