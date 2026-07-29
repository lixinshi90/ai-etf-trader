#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_trades_db.py

Windows/PowerShell 友好：检查 data/trade_history.db 中 trades / daily_equity 情况。

运行：
  cd "D:\Quantitative Trading\ai-etf-trader"
  python check_trades_db.py

"""

import os
import sqlite3

DB = os.path.join('data', 'trade_history.db')


def main():
    print('cwd =', os.getcwd())
    print('db path =', DB)
    print('db exists =', os.path.exists(DB))
    if not os.path.exists(DB):
        return

    con = sqlite3.connect(DB)
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('trades','daily_equity')")
        print('tables =', cur.fetchall())

        # trades
        try:
            cur.execute('SELECT count(1) FROM trades')
            n = cur.fetchone()[0]
            print('trades count =', n)
            cur.execute('SELECT date, etf_code, action, price, quantity, value FROM trades ORDER BY datetime(date) DESC LIMIT 10')
            rows = cur.fetchall()
            print('latest 10 trades:')
            for r in rows:
                print(' ', r)
        except Exception as e:
            print('trades query error:', e)

        # daily_equity
        try:
            cur.execute('SELECT count(1), min(date), max(date) FROM daily_equity')
            print('daily_equity (count,min,max)=', cur.fetchone())
            cur.execute('SELECT date, equity FROM daily_equity ORDER BY date DESC LIMIT 10')
            rows = cur.fetchall()
            print('latest 10 daily_equity:')
            for r in rows:
                print(' ', r)
        except Exception as e:
            print('daily_equity query error:', e)

    finally:
        con.close()


if __name__ == '__main__':
    main()

