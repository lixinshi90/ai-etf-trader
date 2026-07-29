# -*- coding: utf-8 -*-
"""
修正12-22的净值为正确值
"""
import sqlite3

# 基于累加计算的正确净值
correct_equity_22 = 99906.27
date_22 = '2025-12-22'

print(f"修正 {date_22} 的净值\n")
print(f"错误值: 110036.46")
print(f"正确值: {correct_equity_22:.2f}")
print(f"差异: {110036.46 - correct_equity_22:.2f}\n")

print("修正依据:")
print("  - 从初始资金累加所有交易")
print("  - 加上12-22的持仓市值")
print("  - 符合资产延续性原则\n")

response = input("确认修正？(y/n): ")

if response.lower() == 'y':
    conn = sqlite3.connect('data/trade_history.db')
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE daily_equity SET equity = ? WHERE date = ?",
        (correct_equity_22, date_22)
    )
    
    conn.commit()
    conn.close()
    
    print(f"\n✓ 已更新 {date_22} 的净值为 {correct_equity_22:.2f}")
    print("\n修正后的资产变化:")
    print(f"  12-19: 99275.50")
    print(f"  12-22: 99906.27")
    print(f"  变化: +630.77 (+0.63%)")
    print("\n✓ 波动恢复正常范围")
else:
    print("\n取消修正")

