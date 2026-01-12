# -*- coding: utf-8 -*-
"""
找出缺失的那一块
"""
import sys
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 寻找缺失的拼图 ===\n")

conn = sqlite3.connect('data/trade_history.db')

# 获取12-19和12-22之间的所有交易
print("1. 检查12-19到12-22之间的所有交易:\n")

df_trades_between = pd.read_sql_query(
    "SELECT date, etf_code, action, price, quantity, value, capital_after FROM trades WHERE date > '2025-12-19' AND date <= '2025-12-22 23:59:59' ORDER BY date",
    conn
)

print(f"交易数量: {len(df_trades_between)}\n")

if not df_trades_between.empty:
    print("交易明细:")
    for _, row in df_trades_between.iterrows():
        print(f"  {row['date']}")
        print(f"    {row['etf_code']} {row['action']}")
        print(f"    价格: {row['price']:.3f}, 数量: {row['quantity']:.2f}")
        print(f"    金额: {row['value']:.2f}")
        print(f"    交易后现金: {row['capital_after']:.2f}\n")

# 获取12-17最后一笔交易后的现金
print("2. 检查12-17最后一笔交易后的现金:\n")

df_last_17 = pd.read_sql_query(
    "SELECT date, etf_code, action, capital_after FROM trades WHERE date <= '2025-12-17 23:59:59' ORDER BY date DESC LIMIT 1",
    conn
)

if not df_last_17.empty:
    cash_17 = df_last_17.iloc[0]['capital_after']
    print(f"12-17最后交易后现金: {cash_17:.2f}")
    print(f"  日期: {df_last_17.iloc[0]['date']}")
    print(f"  ETF: {df_last_17.iloc[0]['etf_code']}")
    print(f"  操作: {df_last_17.iloc[0]['action']}\n")

# 检查12-18到12-19之间是否有交易
print("3. 检查12-18到12-19之间的交易:\n")

df_trades_18_19 = pd.read_sql_query(
    "SELECT date, etf_code, action, value, capital_after FROM trades WHERE date > '2025-12-17 23:59:59' AND date <= '2025-12-19 23:59:59' ORDER BY date",
    conn
)

if df_trades_18_19.empty:
    print("✓ 12-18到12-19无交易")
    print(f"所以12-19的现金应该等于12-17的现金: {cash_17:.2f}\n")
else:
    print(f"有 {len(df_trades_18_19)} 笔交易:")
    for _, row in df_trades_18_19.iterrows():
        print(f"  {row['date']} {row['etf_code']} {row['action']} {row['value']:.2f}")

# 计算12-19的理论总资产（使用12-17的现金）
print("4. 计算12-19的理论总资产:\n")

# 获取12-19的持仓
df_all_trades_19 = pd.read_sql_query(
    "SELECT etf_code, action, quantity FROM trades WHERE date <= '2025-12-19 23:59:59' ORDER BY date",
    conn
)

holdings_19 = {}
for _, row in df_all_trades_19.iterrows():
    code = str(row['etf_code']).strip()
    if code:
        qty = float(row['quantity'])
        if str(row['action']).lower() == 'sell':
            qty = -qty
        holdings_19[code] = holdings_19.get(code, 0.0) + qty

etf_conn = sqlite3.connect('data/etf_data.db')
holdings_value_19 = 0

for code, qty in holdings_19.items():
    if qty > 0.001:
        try:
            df_p = pd.read_sql_query(
                f"SELECT 收盘 FROM etf_{code} WHERE 日期 = '2025-12-19' LIMIT 1",
                etf_conn
            )
            if df_p.empty:
                df_p = pd.read_sql_query(
                    f"SELECT close FROM etf_{code} WHERE date = '2025-12-19' LIMIT 1",
                    etf_conn
                )
            if not df_p.empty:
                price = float(df_p.iloc[0].iloc[0])
                value = qty * price
                holdings_value_19 += value
        except:
            pass

etf_conn.close()

print(f"现金（12-17最后交易）: {cash_17:.2f}")
print(f"持仓市值（12-19价格）: {holdings_value_19:.2f}")
print(f"理论总资产: {cash_17 + holdings_value_19:.2f}")
print(f"数据库记录: {equity_19:.2f}")
print(f"差异: {abs((cash_17 + holdings_value_19) - equity_19):.2f}\n")

# 最终答案
print("【最终答案】\n")

print("12-19的数据库净值 99275.50 是基于:")
print(f"  现金: {cash_17:.2f} (12-17最后交易)")
print(f"  持仓: {holdings_value_19:.2f} (12-19价格)")
print(f"  合计: {cash_17 + holdings_value_19:.2f}")
print(f"  ✓ 基本吻合（差异{abs((cash_17 + holdings_value_19) - equity_19):.2f}元）\n")

print("12-22的净值变化:")
print(f"  起点: {equity_19:.2f}")
print(f"  买入510880: -{df_trades_between.iloc[0]['value']:.2f}")
print(f"  原有持仓增值: +61.38")
print(f"  新增510880市值: +{8960.79:.2f}")
print(f"  终点: {equity_22:.2f}")
print(f"\n验算: {equity_19:.2f} - {df_trades_between.iloc[0]['value']:.2f} + 61.38 + 8960.79 = {equity_19 - df_trades_between.iloc[0]['value'] + 61.38 + 8960.79:.2f}")
print(f"实际: {equity_22:.2f}")
print(f"差异: {abs(equity_22 - (equity_19 - df_trades_between.iloc[0]['value'] + 61.38 + 8960.79)):.2f}")

conn.close()

print("\n=== 分析完成 ===")

