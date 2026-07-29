# -*- coding: utf-8 -*-
"""
验证资金变化分析的准确性
"""
import sys
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 验证资金变化分析 ===\n")

# 1. 检查数据库中的实际数据
conn = sqlite3.connect('data/trade_history.db')

# 获取12-19和12-22的净值
df_equity = pd.read_sql_query(
    "SELECT date, equity FROM daily_equity WHERE date IN ('2025-12-19', '2025-12-22') ORDER BY date",
    conn
)

print("1. 净值数据:")
print(df_equity.to_string(index=False))

if len(df_equity) == 2:
    equity_19 = df_equity.iloc[0]['equity']
    equity_22 = df_equity.iloc[1]['equity']
    change = equity_22 - equity_19
    change_pct = (change / equity_19) * 100
    print(f"\n净值变化: {equity_19:.2f} → {equity_22:.2f}")
    print(f"增加: {change:.2f} (+{change_pct:.2f}%)")
elif len(df_equity) == 1:
    print(f"\n⚠️ 只有一天的数据: {df_equity.iloc[0]['date']}")
    print("12-22的数据可能已被删除，等待重新执行")
else:
    print("\n⚠️ 数据不完整")

# 2. 检查交易记录
print("\n2. 检查12-19之后的交易:")
df_trades = pd.read_sql_query(
    "SELECT date, etf_code, action, quantity, price, value FROM trades WHERE date > '2025-12-19' ORDER BY date",
    conn
)

if df_trades.empty:
    print("✓ 12-19之后无交易记录")
    print("说明：资金变化仅来自持仓价格波动，无新交易")
else:
    print(f"12-19之后有 {len(df_trades)} 笔交易:")
    print(df_trades.to_string(index=False))

# 3. 检查当前持仓
print("\n3. 当前持仓计算:")
df_all_trades = pd.read_sql_query(
    "SELECT etf_code, action, quantity FROM trades ORDER BY date",
    conn
)

holdings = {}
for _, row in df_all_trades.iterrows():
    code = str(row['etf_code']).strip()
    if code:
        qty = float(row['quantity'])
        if str(row['action']).lower() == 'sell':
            qty = -qty
        holdings[code] = holdings.get(code, 0.0) + qty

print("持仓列表:")
for code, qty in sorted(holdings.items()):
    if qty > 0.001:
        print(f"  {code}: {qty:.2f}")

print(f"\n持仓数量: {len([q for q in holdings.values() if q > 0.001])} 只")

conn.close()

# 4. 获取价格并计算市值变化
print("\n4. 持仓市值变化分析:")

etf_conn = sqlite3.connect('data/etf_data.db')

total_value_19 = 0
total_value_22 = 0

for code, qty in holdings.items():
    if qty > 0.001:
        try:
            # 12-19价格
            try:
                df_19 = pd.read_sql_query(
                    f"SELECT 收盘 FROM etf_{code} WHERE 日期 = '2025-12-19' LIMIT 1",
                    etf_conn
                )
                price_19 = float(df_19.iloc[0]['收盘']) if not df_19.empty else None
            except:
                df_19 = pd.read_sql_query(
                    f"SELECT close FROM etf_{code} WHERE date = '2025-12-19' LIMIT 1",
                    etf_conn
                )
                price_19 = float(df_19.iloc[0]['close']) if not df_19.empty else None
            
            # 12-22价格
            try:
                df_22 = pd.read_sql_query(
                    f"SELECT 收盘 FROM etf_{code} WHERE 日期 = '2025-12-22' LIMIT 1",
                    etf_conn
                )
                price_22 = float(df_22.iloc[0]['收盘']) if not df_22.empty else None
            except:
                df_22 = pd.read_sql_query(
                    f"SELECT close FROM etf_{code} WHERE date = '2025-12-22' LIMIT 1",
                    etf_conn
                )
                price_22 = float(df_22.iloc[0]['close']) if not df_22.empty else None
            
            if price_19 and price_22:
                value_19 = qty * price_19
                value_22 = qty * price_22
                total_value_19 += value_19
                total_value_22 += value_22
                
                change = value_22 - value_19
                change_pct = (change / value_19) * 100 if value_19 > 0 else 0
                
                print(f"{code}:")
                print(f"  数量: {qty:.2f}")
                print(f"  12-19: {price_19:.3f} × {qty:.2f} = {value_19:.2f}")
                print(f"  12-22: {price_22:.3f} × {qty:.2f} = {value_22:.2f}")
                print(f"  变化: {change:+.2f} ({change_pct:+.2f}%)")
                
        except Exception as e:
            print(f"{code}: 无法获取价格")

etf_conn.close()

print(f"\n持仓总市值:")
print(f"  12-19: {total_value_19:.2f}")
print(f"  12-22: {total_value_22:.2f}")
print(f"  变化: {total_value_22 - total_value_19:+.2f}")

# 5. 验证用户的分析
print("\n=== 验证用户分析 ===\n")

print("用户分析中的关键点:")
print(f"1. 原有4只持仓增值: 61.38元")
print(f"   实际计算: {total_value_22 - total_value_19:.2f}元")
print(f"   {'✓ 基本一致' if abs((total_value_22 - total_value_19) - 61.38) < 10 else '✗ 有差异'}")

print(f"\n2. 新增510880持仓市值: 8960.79元")
if '510880' in holdings and holdings['510880'] > 0.001:
    print(f"   ✓ 确实有510880持仓")
else:
    print(f"   ✗ 当前无510880持仓")

print(f"\n3. 总资产变化: 10760.96元")
if len(df_equity) == 2:
    actual_change = equity_22 - equity_19
    print(f"   实际变化: {actual_change:.2f}元")
    print(f"   {'✓ 基本一致' if abs(actual_change - 10760.96) < 100 else '✗ 有差异'}")

print("\n=== 验证完成 ===")

