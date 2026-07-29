# -*- coding: utf-8 -*-
"""
修正12月19日的净值
"""
import sqlite3

correct_equity_19 = 121756.97
date_19 = '2025-12-19'

print(f"修正 {date_19} 的净值")
print(f"错误值: 99275.50")
print(f"正确值: {correct_equity_19:.2f}\n")

response = input("确认修正？(y/n): ")

if response.lower() == 'y':
    conn = sqlite3.connect('data/trade_history.db')
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE daily_equity SET equity = ? WHERE date = ?",
        (correct_equity_19, date_19)
    )
    
    conn.commit()
    conn.close()
    
    print(f"\n✓ 已更新 {date_19} 的净值为 {correct_equity_19:.2f}")
    print("\n修正后的资产变化:")
    print(f"  12-19: 121756.97")
    print(f"  12-22: 110036.46")
    print(f"  变化: -11720.51 (-9.6%)")
else:
    print("\n取消修正")

