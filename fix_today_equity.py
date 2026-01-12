# -*- coding: utf-8 -*-
"""
修正今日净值为正确值
"""
import sys
import sqlite3

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 修正今日净值 ===\n")

# 正确的今日净值
correct_equity = 121818.35
today = '2025-12-22'

print(f"日期: {today}")
print(f"错误净值: 110049.91")
print(f"正确净值: {correct_equity:.2f}")
print(f"差异: {correct_equity - 110049.91:.2f}\n")

response = input("确认修正？(y/n): ")

if response.lower() == 'y':
    conn = sqlite3.connect('data/trade_history.db')
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE daily_equity SET equity = ? WHERE date = ?",
        (correct_equity, today)
    )
    
    conn.commit()
    conn.close()
    
    print(f"\n✓ 已更新 {today} 的净值为 {correct_equity:.2f}")
else:
    print("\n取消修正")

