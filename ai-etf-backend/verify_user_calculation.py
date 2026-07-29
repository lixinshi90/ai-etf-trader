# -*- coding: utf-8 -*-
"""
验证用户的计算：99275.50 - 8974.23 + 62.17 + 8960.79 + 1738.00 = 101062.23
"""
import sys
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 验证用户计算 ===\n")

# 用户的计算公式
base = 99275.50  # 12-19净值
buy_cost = 8974.23  # 买入510880成本
price_gain = 62.17  # 原有持仓增值（用户数据）
new_holding = 8960.79  # 新增510880市值
unknown = 1738.00  # 未知项

user_result = base - buy_cost + price_gain + new_holding + unknown
print("用户计算公式:")
print(f"  99275.50 (12-19净值)")
print(f"  - 8974.23 (买入510880成本)")
print(f"  + 62.17 (原有持仓增值)")
print(f"  + 8960.79 (新增510880市值)")
print(f"  + 1738.00 (未知项)")
print(f"  = {user_result:.2f}\n")

# 实际数据库数据
conn = sqlite3.connect('data/trade_history.db')

df_equity = pd.read_sql_query(
    "SELECT date, equity FROM daily_equity WHERE date IN ('2025-12-19', '2025-12-22') ORDER BY date",
    conn
)

equity_19 = df_equity[df_equity['date'] == '2025-12-19'].iloc[0]['equity']
equity_22 = df_equity[df_equity['date'] == '2025-12-22'].iloc[0]['equity']

print("实际数据库数据:")
print(f"  12-19净值: {equity_19:.2f}")
print(f"  12-22净值: {equity_22:.2f}")
print(f"  差异: {equity_22 - equity_19:.2f}\n")

# 检查12-19的现金是否真的是81030.56
print("【关键检查】12-19的现金来源\n")

# 方法1: 从capital_after读取
df_last_trade_19 = pd.read_sql_query(
    "SELECT date, etf_code, action, capital_after FROM trades WHERE date <= '2025-12-19 23:59:59' ORDER BY date DESC LIMIT 1",
    conn
)

if not df_last_trade_19.empty:
    cash_from_db = df_last_trade_19.iloc[0]['capital_after']
    print(f"方法1 - 从最后一笔交易的capital_after:")
    print(f"  日期: {df_last_trade_19.iloc[0]['date']}")
    print(f"  ETF: {df_last_trade_19.iloc[0]['etf_code']}")
    print(f"  操作: {df_last_trade_19.iloc[0]['action']}")
    print(f"  现金: {cash_from_db:.2f}\n")

# 方法2: 从初始资金累加所有交易
print("方法2 - 从初始资金累加所有交易:")
initial_capital = 100000.0
cash_calculated = initial_capital

df_all_trades = pd.read_sql_query(
    "SELECT date, etf_code, action, value FROM trades WHERE date <= '2025-12-19 23:59:59' ORDER BY date",
    conn
)

for _, row in df_all_trades.iterrows():
    action = str(row['action']).lower()
    value = float(row['value'])
    if action == 'buy':
        cash_calculated -= value
    elif action == 'sell':
        cash_calculated += value

print(f"  初始资金: {initial_capital:.2f}")
print(f"  累加后现金: {cash_calculated:.2f}\n")

# 计算12-19的持仓市值
print("【计算12-19持仓市值】\n")

holdings_19 = {}
for _, row in df_all_trades.iterrows():
    code = str(row['etf_code']).strip()
    if code:
        # 需要从trades表获取quantity
        pass

# 重新查询包含quantity的数据
df_all_trades_full = pd.read_sql_query(
    "SELECT etf_code, action, quantity FROM trades WHERE date <= '2025-12-19 23:59:59' ORDER BY date",
    conn
)

holdings_19 = {}
for _, row in df_all_trades_full.iterrows():
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
                print(f"  {code}: {qty:.2f} × {price:.3f} = {value:.2f}")
        except:
            pass

print(f"\n持仓市值总计: {holdings_value_19:.2f}\n")

etf_conn.close()
conn.close()

# 总结
print("【总结】12-19的真实资产结构\n")
print(f"现金（从capital_after）: {cash_from_db:.2f}")
print(f"现金（累加计算）: {cash_calculated:.2f}")
print(f"持仓市值: {holdings_value_19:.2f}")
print(f"\n理论总资产（capital_after）: {cash_from_db + holdings_value_19:.2f}")
print(f"理论总资产（累加计算）: {cash_calculated + holdings_value_19:.2f}")
print(f"数据库记录: {equity_19:.2f}")
print(f"\n差异分析:")
print(f"  使用capital_after的差异: {abs((cash_from_db + holdings_value_19) - equity_19):.2f}")
print(f"  使用累加计算的差异: {abs((cash_calculated + holdings_value_19) - equity_19):.2f}")

print("\n=== 验证完成 ===")

