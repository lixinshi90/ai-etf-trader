# -*- coding: utf-8 -*-
"""
清除Flask缓存并验证数据
"""
import sys
import os
import shutil
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 清除缓存并验证数据 ===\n")

# 1. 清除Flask缓存
cache_dir = '.cache'
if os.path.exists(cache_dir):
    try:
        shutil.rmtree(cache_dir)
        print(f"✓ 已删除缓存目录: {cache_dir}")
    except Exception as e:
        print(f"✗ 删除缓存失败: {e}")
else:
    print(f"缓存目录不存在: {cache_dir}")

# 2. 验证数据库中的实际数据
print("\n验证数据库数据:\n")

conn = sqlite3.connect('data/trade_history.db')

df_equity = pd.read_sql_query(
    "SELECT date, equity FROM daily_equity WHERE date >= '2025-12-15' ORDER BY date",
    conn
)

print("最近的净值记录:")
print(df_equity.to_string(index=False))

print(f"\n12-22的净值: {df_equity[df_equity['date'] == '2025-12-22'].iloc[0]['equity']:.2f}")

conn.close()

print("\n提示:")
print("1. Flask缓存已清除")
print("2. 请重启Web服务: python -m src.web_app")
print("3. 在浏览器中按 Ctrl + Shift + Delete 清除浏览器缓存")
print("4. 或使用无痕模式打开: Ctrl + Shift + N (Chrome)")
print("5. 访问: http://127.0.0.1:5001")

print("\n=== 完成 ===")

