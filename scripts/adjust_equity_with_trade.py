# -*- coding: utf-8 -*-
"""
以“当天一笔调整交易 + 日终快照”替代直接回撤：
- 仅作用于指定日期，不改动之前任何数据；尤其不会把前一日资金重置为 100000。
- 在 trades 表插入一条 action='adjust' 的记录，etf_code='ADJ'，price=0，quantity=0，value=0，capital_after=目标净值；
- 同时在 daily_equity 表 upsert 当日净值（用于绩效曲线），不改动其他日期。

用法：
  uv run python -m scripts.adjust_equity_with_trade --date 2025-12-11 --equity 252900.93 --note "回撤替代"
  # 或在 qlib-venv 中直接用 python 运行亦可
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime

from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB = os.path.join(ROOT, "data", "trade_history.db")


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            etf_code TEXT,
            action TEXT,
            price REAL,
            quantity REAL,
            value REAL,
            capital_after REAL,
            reasoning TEXT
        )
        """
    )
    conn.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")


MESSAGE = """
注意：本脚本只在指定日期插入一条调整交易，并 upsert 当日日终净值；不修改其他日期的数据。
如需撤销，可删除该日期的 daily_equity 记录，并删除 trades 中 action='adjust' 的该行。
"""


def main():
    load_dotenv(override=True)
    ap = argparse.ArgumentParser(description="以当天一笔调整交易替代回撤")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--equity", required=True, type=float, help="该日目标日终净值")
    ap.add_argument("--note", default="adjust by script", help="备注/原因")
    args = ap.parse_args()

    try:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
    except Exception:
        raise SystemExit("--date 必须是 YYYY-MM-DD")

    ts = f"{d.strftime('%Y-%m-%d')} 15:00:00"
    os.makedirs(os.path.dirname(DB), exist_ok=True)

    conn = sqlite3.connect(DB)
    try:
        ensure_tables(conn)
        # 插入一条调整交易（不改变持仓，仅记录当日结束后的资金）
        conn.execute(
            """
            INSERT INTO trades(date, etf_code, action, price, quantity, value, capital_after, reasoning)
            VALUES (?, 'ADJ', 'adjust', 0, 0, 0, ?, ?)
            """,
            (ts, float(args.equity), args.note),
        )
        # upsert 当日 daily_equity
        conn.execute(
            """
            INSERT INTO daily_equity(date, equity) VALUES(?,?)
            ON CONFLICT(date) DO UPDATE SET equity=excluded.equity
            """,
            (d.strftime("%Y-%m-%d"), float(args.equity)),
        )
        conn.commit()
        print("✅ 已写入调整交易与当日绩效：", d.strftime("%Y-%m-%d"), float(args.equity))
        print(MESSAGE)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

