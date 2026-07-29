#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_trade_history_equity.py

把 data/trade_history.db 的 daily_equity 表按“正确净值”批量修正。

特点：
- 自动备份 DB -> data/trade_history.db.bak_equity_fix
- 仅更新 daily_equity.date 在映射表中的行
- 更新后打印最近 20 条用于核对

使用（在项目根目录）：
  python fix_trade_history_equity.py

"""

from __future__ import annotations

import os
import shutil
import sqlite3
from typing import Dict

DB_PATH = os.path.join('data', 'trade_history.db')
BACKUP_PATH = os.path.join('data', 'trade_history.db.bak_equity_fix')

# 你给定的“正确净值”（全部控制在9万~10万区间）
CORRECT_NAV: Dict[str, float] = {
    '2025-11-26': 100000.00,
    '2025-11-27': 99559.67,
    '2025-11-28': 99135.43,
    '2025-11-30': 99344.03,
    '2025-12-01': 99394.43,
    '2025-12-02': 98778.42,
    '2025-12-03': 98296.48,
    '2025-12-05': 99118.55,
    '2025-12-07': 99411.59,
    '2025-12-08': 99411.59,
    '2025-12-09': 97746.13,
    '2025-12-11': 97081.57,
    '2025-12-12': 98436.43,
    '2025-12-14': 99777.74,
    '2025-12-15': 99777.74,
    '2025-12-16': 99382.11,
    '2025-12-17': 99646.61,
    '2025-12-18': 99499.70,
    '2025-12-19': 99844.89,
    '2025-12-22': 99906.27,
    '2025-12-23': 99795.48,
}


def backup_db() -> None:
    if not os.path.exists(DB_PATH):
        raise SystemExit(f'找不到数据库: {DB_PATH}')
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f'[fix_equity] 已备份数据库: {BACKUP_PATH}')


def ensure_table(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_equity'")
    row = cur.fetchone()
    if not row:
        raise SystemExit('数据库中不存在 daily_equity 表，无法修正。')


def apply_fix() -> None:
    backup_db()

    con = sqlite3.connect(DB_PATH)
    try:
        ensure_table(con)
        cur = con.cursor()

        # 统计现有日期
        cur.execute('SELECT date, equity FROM daily_equity')
        existing = {d: float(e) for (d, e) in cur.fetchall()}

        to_update = []
        missing = []
        for d, new_eq in CORRECT_NAV.items():
            if d in existing:
                old_eq = existing[d]
                to_update.append((new_eq, d, old_eq))
            else:
                missing.append(d)

        # 执行更新
        updated = 0
        for new_eq, d, old_eq in to_update:
            cur.execute('UPDATE daily_equity SET equity = ? WHERE date = ?', (float(new_eq), d))
            updated += cur.rowcount
            print(f'[fix_equity] {d}: {old_eq:.6f} -> {new_eq:.2f}')

        con.commit()
        print(f'\n[fix_equity] 更新完成：共更新 {updated} 行。')

        if missing:
            print('\n[fix_equity] 警告：以下日期在 daily_equity 不存在（未插入，仅提示）：')
            for d in missing:
                print('  -', d)

        # 打印最新 20 行核对
        cur.execute('SELECT date, equity FROM daily_equity ORDER BY date DESC LIMIT 20')
        rows = cur.fetchall()
        print('\n[fix_equity] latest daily_equity (top 20):')
        for r in rows:
            print(r)

    finally:
        con.close()


if __name__ == '__main__':
    apply_fix()

