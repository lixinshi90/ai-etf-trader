#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将指定日期的每日净值替换为“上一可用交易日”的净值。
使用场景：某几天未真实交易，误写入了不合规/虚高净值，希望用前一日净值替换。

用法示例：
  uv run python -m tools.copy_prev_equity --dates 2025-12-07,2025-12-14
  uv run python -m tools.copy_prev_equity --db data/trade_history.db --dates 2025-12-07

说明：
- 对于每个目标日期 D，本脚本会查找 daily_equity 中“< D”的最近一条记录的净值，并写回到 D。
- 若找不到更早日期，跳过并给出提示。
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import List


def copy_prev_equity(db_path: Path, dates: List[str]) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")
        changed = 0
        for d in dates:
            # 找上一可用日期的净值
            cur.execute(
                "SELECT equity FROM daily_equity WHERE date < ? ORDER BY date DESC LIMIT 1",
                (d,)
            )
            row = cur.fetchone()
            if not row:
                print(f"[skip] {d}: 未找到更早日期的净值，未修改")
                continue
            prev_eq = float(row[0])
            # 若目标日不存在，先插入再更新（INSERT OR IGNORE）
            cur.execute("INSERT OR IGNORE INTO daily_equity(date, equity) VALUES(?, ?)", (d, prev_eq))
            # 再覆盖为前一日净值
            cur.execute("UPDATE daily_equity SET equity=? WHERE date=?", (prev_eq, d))
            changed += 1
            print(f"[ok] {d}: 设置为上一日净值 {prev_eq:.2f}")
        conn.commit()
        return changed
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="将指定日期的净值替换为上一可用日期的净值")
    ap.add_argument("--db", type=Path, default=Path("data/trade_history.db"), help="数据库路径")
    ap.add_argument("--dates", type=str, required=True, help="逗号分隔的日期列表，如 2025-12-07,2025-12-14")
    args = ap.parse_args()

    dates = [s.strip() for s in args.dates.split(',') if s.strip()]
    if not dates:
        print("[error] 未提供有效日期")
        return 1

    n = copy_prev_equity(args.db, dates)
    print(f"=== 完成：{n} 个日期已被修正 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

