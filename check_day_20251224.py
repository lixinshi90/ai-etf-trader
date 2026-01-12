#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_day_20251224.py

检查 trade_history.db 中 2025-12-24 是否：
- 已写入 daily_equity
- 写入了 trades

Windows/Powershell 友好：避免 -c 引号问题。

运行：
  cd "D:\Quantitative Trading\ai-etf-trader"
  python check_day_20251224.py
"""

import sqlite3

DB = r"data\trade_history.db"
DAY = "2025-12-24"


def main():
    con = sqlite3.connect(DB)
    try:
        cur = con.cursor()

        cur.execute("SELECT date, equity FROM daily_equity WHERE date=?", (DAY,))
        print("daily_equity", DAY, "=", cur.fetchone())

        cur.execute(
            "SELECT date, etf_code, action, price, quantity, value, capital_after "
            "FROM trades WHERE date LIKE ? ORDER BY datetime(date) ASC",
            (DAY + "%",),
        )
        rows = cur.fetchall()
        print("trades", DAY, "rows=", len(rows))
        for r in rows[:20]:
            print(" ", r)
        if len(rows) > 20:
            print(" ...")

    finally:
        con.close()


if __name__ == "__main__":
    main()

