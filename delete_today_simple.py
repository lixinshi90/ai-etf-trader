# -*- coding: utf-8 -*-
import sqlite3

today = '2025-12-22'

print(f"删除 {today} 的数据...")

conn = sqlite3.connect('data/trade_history.db')
cursor = conn.cursor()

# 删除今日净值
cursor.execute("DELETE FROM daily_equity WHERE date = ?", (today,))
print(f"删除净值记录: {cursor.rowcount} 条")

# 删除今日交易
cursor.execute("DELETE FROM trades WHERE date >= ?", (today,))
print(f"删除交易记录: {cursor.rowcount} 笔")

conn.commit()
conn.close()

print("完成！")

