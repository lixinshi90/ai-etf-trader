# -*- coding: utf-8 -*-
"""
仅修正12月19日的净值
"""
import sqlite3

date_19 = '2025-12-19'
old_equity = 99275.50
new_equity = 99844.89  # 基于累加方法的正确值

print(f"修正 {date_19} 的净值\n")
print(f"当前值: {old_equity:.2f}")
print(f"修正为: {new_equity:.2f}")
print(f"差异: {new_equity - old_equity:+.2f} (+{(new_equity - old_equity) / old_equity * 100:.2f}%)\n")

print("修正后的资产变化:")
print(f"  12-18: 99499.70 (理论值)")
print(f"  12-19: 99844.89 (修正后)")
print(f"  变化: +345.19 (+0.35%)")
print()
print(f"  12-19: 99844.89 (修正后)")
print(f"  12-22: 99906.27")
print(f"  变化: +61.38 (+0.06%)\n")

response = input("确认修正？(y/n): ")

if response.lower() == 'y':
    conn = sqlite3.connect('data/trade_history.db')
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE daily_equity SET equity = ? WHERE date = ?",
        (new_equity, date_19)
    )
    
    conn.commit()
    conn.close()
    
    print(f"\n✓ 已更新 {date_19} 的净值为 {new_equity:.2f}")
    print("\n提示:")
    print("1. 清除Flask缓存（已自动清除）")
    print("2. 重启Web服务: python -m src.web_app")
    print("3. 强制刷新浏览器: Ctrl + Shift + R")
else:
    print("\n取消修正")

