# -*- coding: utf-8 -*-
"""
删除今日数据，准备重新执行任务
"""
import sys
import sqlite3

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 删除今日数据 ===\n")

today = '2025-12-22'

conn = sqlite3.connect('data/trade_history.db')
cursor = conn.cursor()

# 检查今日数据
cursor.execute("SELECT COUNT(*) FROM daily_equity WHERE date = ?", (today,))
equity_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM trades WHERE date >= ?", (today,))
trades_count = cursor.fetchone()[0]

print(f"今日净值记录: {equity_count} 条")
print(f"今日交易记录: {trades_count} 笔\n")

if equity_count == 0 and trades_count == 0:
    print("✓ 今日无数据，无需删除")
    conn.close()
    sys.exit(0)

response = input(f"确认删除今日（{today}）的所有数据？(y/n): ")

if response.lower() == 'y':
    # 删除今日净值
    cursor.execute("DELETE FROM daily_equity WHERE date = ?", (today,))
    deleted_equity = cursor.rowcount
    
    # 删除今日交易
    cursor.execute("DELETE FROM trades WHERE date >= ?", (today,))
    deleted_trades = cursor.rowcount
    
    conn.commit()
    
    print(f"\n✓ 已删除:")
    print(f"  - 净值记录: {deleted_equity} 条")
    print(f"  - 交易记录: {deleted_trades} 笔")
    print(f"\n数据库已准备好重新执行任务")
else:
    print("\n取消删除")

conn.close()

