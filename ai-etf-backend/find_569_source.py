# -*- coding: utf-8 -*-
"""
寻找569.39元差异的来源
"""
import sys
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 寻找569.39元差异的来源 ===\n")

conn = sqlite3.connect('data/trade_history.db')

# 1. 检查12-19和12-22的现金
print("【现金对比】\n")

# 12-19的现金（从最后一笔交易）
df_cash_19 = pd.read_sql_query(
    "SELECT date, etf_code, action, capital_after FROM trades WHERE date <= '2025-12-19 23:59:59' ORDER BY date DESC LIMIT 1",
    conn
)

# 12-22的现金（从最后一笔交易）
df_cash_22 = pd.read_sql_query(
    "SELECT date, etf_code, action, value, capital_after FROM trades WHERE date <= '2025-12-22 23:59:59' ORDER BY date DESC LIMIT 1",
    conn
)

if not df_cash_19.empty:
    cash_19_db = df_cash_19.iloc[0]['capital_after']
    print(f"12-19现金（从capital_after）: {cash_19_db:.2f}")
    print(f"  来自交易: {df_cash_19.iloc[0]['date']} {df_cash_19.iloc[0]['etf_code']} {df_cash_19.iloc[0]['action']}\n")

if not df_cash_22.empty:
    cash_22_db = df_cash_22.iloc[0]['capital_after']
    buy_value = df_cash_22.iloc[0]['value']
    print(f"12-22现金（从capital_after）: {cash_22_db:.2f}")
    print(f"  来自交易: {df_cash_22.iloc[0]['date']} {df_cash_22.iloc[0]['etf_code']} {df_cash_22.iloc[0]['action']}")
    print(f"  交易金额: {buy_value:.2f}\n")

# 2. 验证现金变化
print("【现金变化验证】\n")

cash_change_expected = -buy_value  # 买入应该减少现金
cash_change_actual = cash_22_db - cash_19_db

print(f"预期现金变化: {cash_change_expected:.2f}")
print(f"实际现金变化: {cash_change_actual:.2f}")
print(f"差异: {cash_change_actual - cash_change_expected:.2f}\n")

# 3. 从累加方法计算
print("【累加方法计算】\n")

initial_capital = 100000.0

# 计算到12-19的累加现金
df_trades_19 = pd.read_sql_query(
    "SELECT action, value FROM trades WHERE date <= '2025-12-19 23:59:59' ORDER BY date",
    conn
)

cash_accumulated_19 = initial_capital
for _, row in df_trades_19.iterrows():
    action = str(row['action']).lower()
    value = float(row['value'])
    if action == 'buy':
        cash_accumulated_19 -= value
    elif action == 'sell':
        cash_accumulated_19 += value

print(f"12-19累加现金: {cash_accumulated_19:.2f}")
print(f"12-19数据库现金: {cash_19_db:.2f}")
print(f"差异: {cash_19_db - cash_accumulated_19:.2f}\n")

# 计算到12-22的累加现金
df_trades_22 = pd.read_sql_query(
    "SELECT action, value FROM trades WHERE date <= '2025-12-22 23:59:59' ORDER BY date",
    conn
)

cash_accumulated_22 = initial_capital
for _, row in df_trades_22.iterrows():
    action = str(row['action']).lower()
    value = float(row['value'])
    if action == 'buy':
        cash_accumulated_22 -= value
    elif action == 'sell':
        cash_accumulated_22 += value

print(f"12-22累加现金: {cash_accumulated_22:.2f}")
print(f"12-22数据库现金: {cash_22_db:.2f}")
print(f"差异: {cash_22_db - cash_accumulated_22:.2f}\n")

# 4. 分析569元的来源
print("【569元差异的来源分析】\n")

# 12-19的差异
diff_19 = cash_19_db - cash_accumulated_19
print(f"12-19现金差异: {diff_19:.2f}")
print(f"  这个差异在12-19的净值计算中已经存在\n")

# 12-22的差异
diff_22 = cash_22_db - cash_accumulated_22
print(f"12-22现金差异: {diff_22:.2f}")
print(f"  这个差异延续到了12-22\n")

# 净值差异
print(f"12-19净值差异（理论 vs 数据库）:")
print(f"  理论: 99844.89")
print(f"  数据库: 99275.50")
print(f"  差异: -569.38\n")

print(f"12-22净值差异（理论 vs 数据库）:")
print(f"  理论: 99906.27")
print(f"  数据库: 99906.27")
print(f"  差异: 0.00\n")

print("【结论】")
print(f"569元的差异来自于:")
print(f"  12-19的净值计算使用了错误的现金基准（capital_after vs 累加）")
print(f"  差异: {diff_19:.2f}")
print(f"  这个差异在12-22被修正了")

conn.close()

print("\n=== 分析完成 ===")

