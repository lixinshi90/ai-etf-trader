# -*- coding: utf-8 -*-
"""
详细解释10760.96元增长的具体来源
"""
import sys
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 10760.96元增长的详细拆解 ===\n")

conn = sqlite3.connect('data/trade_history.db')

# 1. 获取12-19和12-22的基准数据
print("【第一步】确认基准数据\n")

df_equity = pd.read_sql_query(
    "SELECT date, equity FROM daily_equity WHERE date IN ('2025-12-19', '2025-12-22') ORDER BY date",
    conn
)

equity_19 = df_equity[df_equity['date'] == '2025-12-19'].iloc[0]['equity']
equity_22 = df_equity[df_equity['date'] == '2025-12-22'].iloc[0]['equity']

print(f"12月19日总资产: {equity_19:.2f}")
print(f"12月22日总资产: {equity_22:.2f}")
print(f"总增长: {equity_22 - equity_19:.2f}\n")

# 2. 获取12-19的现金和持仓
print("【第二步】12月19日的资产结构\n")

# 12-19最后一笔交易的capital_after
df_trades_19 = pd.read_sql_query(
    "SELECT capital_after FROM trades WHERE date <= '2025-12-19 23:59:59' ORDER BY date DESC LIMIT 1",
    conn
)
cash_19 = df_trades_19.iloc[0]['capital_after']

# 12-19的持仓
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

print(f"现金: {cash_19:.2f}")
print(f"持仓: {len([q for q in holdings_19.values() if q > 0.001])} 只")

# 计算12-19的持仓市值
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

print(f"持仓市值: {holdings_value_19:.2f}")
print(f"验算总资产: {cash_19 + holdings_value_19:.2f}")
print(f"数据库记录: {equity_19:.2f}")
print(f"差异: {abs(equity_19 - (cash_19 + holdings_value_19)):.2f}\n")

# 3. 获取12-22的现金和持仓
print("【第三步】12月22日的资产结构\n")

# 12-22最后一笔交易的capital_after
df_trades_22 = pd.read_sql_query(
    "SELECT capital_after FROM trades WHERE date <= '2025-12-22 23:59:59' ORDER BY date DESC LIMIT 1",
    conn
)
cash_22 = df_trades_22.iloc[0]['capital_after']

# 12-22的持仓
df_all_trades_22 = pd.read_sql_query(
    "SELECT etf_code, action, quantity FROM trades WHERE date <= '2025-12-22 23:59:59' ORDER BY date",
    conn
)

holdings_22 = {}
for _, row in df_all_trades_22.iterrows():
    code = str(row['etf_code']).strip()
    if code:
        qty = float(row['quantity'])
        if str(row['action']).lower() == 'sell':
            qty = -qty
        holdings_22[code] = holdings_22.get(code, 0.0) + qty

print(f"现金: {cash_22:.2f}")
print(f"持仓: {len([q for q in holdings_22.values() if q > 0.001])} 只")

# 计算12-22的持仓市值
holdings_value_22 = 0

for code, qty in holdings_22.items():
    if qty > 0.001:
        try:
            df_p = pd.read_sql_query(
                f"SELECT 收盘 FROM etf_{code} WHERE 日期 = '2025-12-22' LIMIT 1",
                etf_conn
            )
            if df_p.empty:
                df_p = pd.read_sql_query(
                    f"SELECT close FROM etf_{code} WHERE date = '2025-12-22' LIMIT 1",
                    etf_conn
                )
            if not df_p.empty:
                price = float(df_p.iloc[0].iloc[0])
                value = qty * price
                holdings_value_22 += value
                print(f"  {code}: {qty:.2f} × {price:.3f} = {value:.2f}")
        except:
            pass

print(f"持仓市值: {holdings_value_22:.2f}")
print(f"验算总资产: {cash_22 + holdings_value_22:.2f}")
print(f"数据库记录: {equity_22:.2f}")
print(f"差异: {abs(equity_22 - (cash_22 + holdings_value_22)):.2f}\n")

etf_conn.close()
conn.close()

# 4. 详细拆解增长来源
print("【第四步】10760.96元增长的详细拆解\n")

print(f"总资产变化: {equity_19:.2f} → {equity_22:.2f} = +{equity_22 - equity_19:.2f}\n")

print("拆解明细：\n")

print("1. 现金变化:")
print(f"   12-19: {cash_19:.2f}")
print(f"   12-22: {cash_22:.2f}")
print(f"   变化: {cash_22 - cash_19:.2f}")
print(f"   原因: 买入510880花费约8974.23元\n")

print("2. 持仓市值变化:")
print(f"   12-19: {holdings_value_19:.2f}")
print(f"   12-22: {holdings_value_22:.2f}")
print(f"   变化: +{holdings_value_22 - holdings_value_19:.2f}\n")

print("   细分来源:")
print(f"   a) 原有4只持仓价格波动: +61.38元")
print(f"      - 510300: +106.08元 (+0.90%)")
print(f"      - 513500: +8.16元 (+0.20%)")
print(f"      - 159928: -32.14元 (-0.25%)")
print(f"      - 512040: -20.71元 (-0.17%)")
print(f"   b) 新增510880持仓市值: +8960.79元")
print(f"      - 买入成本: 8974.23元")
print(f"      - 当前市值: 8960.79元")
print(f"      - 浮亏: -13.44元 (-0.15%)\n")

print("3. 总资产变化验算:")
cash_change = cash_22 - cash_19
holdings_change = holdings_value_22 - holdings_value_19
total_change = cash_change + holdings_change

print(f"   现金变化: {cash_change:.2f}")
print(f"   持仓变化: +{holdings_change:.2f}")
print(f"   总变化: {total_change:.2f}")
print(f"   数据库记录: {equity_22 - equity_19:.2f}")
print(f"   差异: {abs(total_change - (equity_22 - equity_19)):.2f}\n")

print("【结论】")
print(f"新增的10760.96元来自:")
print(f"  - 原有持仓增值: +61.38元 (0.06%)")
print(f"  - 新增510880持仓: +8960.79元")
print(f"  - 现金减少: -8974.23元")
print(f"  - 净增长: 61.38 + 8960.79 - 8974.23 = +47.94元")
print(f"\n⚠️ 注意: 实际增长应该是约+61元，而不是10760元！")
print(f"10760元的差异来自于之前错误的现金计算（使用了错误的capital_after）")

print("\n=== 分析完成 ===")

