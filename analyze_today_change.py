# -*- coding: utf-8 -*-
import sys
import pandas as pd
import sqlite3

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 今日净值变化分析 ===\n")

# 获取昨日和今日净值
conn = sqlite3.connect('data/trade_history.db')
df_equity = pd.read_sql_query(
    "SELECT date, equity FROM daily_equity ORDER BY date DESC LIMIT 2",
    conn
)

today_equity = df_equity.iloc[0]['equity']
yesterday_equity = df_equity.iloc[1]['equity']
change = today_equity - yesterday_equity
change_pct = (change / yesterday_equity) * 100

print(f"昨日净值 ({df_equity.iloc[1]['date']}): {yesterday_equity:.2f}")
print(f"今日净值 ({df_equity.iloc[0]['date']}): {today_equity:.2f}")
print(f"变化: {change:+.2f} ({change_pct:+.2f}%)")

# 获取持仓
df_trades = pd.read_sql_query(
    "SELECT etf_code, action, quantity FROM trades ORDER BY date",
    conn
)

holdings = {}
for _, row in df_trades.iterrows():
    code = str(row['etf_code']).strip()
    if code:
        qty = float(row['quantity'])
        if str(row['action']).lower() == 'sell':
            qty = -qty
        holdings[code] = holdings.get(code, 0.0) + qty

conn.close()

# 获取昨日和今日价格
print("\n=== 持仓价格变化 ===\n")

etf_conn = sqlite3.connect('data/etf_data.db')

total_yesterday_value = 0
total_today_value = 0

for code, qty in holdings.items():
    if qty > 0.001:
        try:
            # 获取昨日价格
            df_yesterday = pd.read_sql_query(
                f"SELECT 收盘 FROM etf_{code} WHERE 日期 = '2025-12-19' LIMIT 1",
                etf_conn
            )
            if df_yesterday.empty:
                df_yesterday = pd.read_sql_query(
                    f"SELECT close FROM etf_{code} WHERE date = '2025-12-19' LIMIT 1",
                    etf_conn
                )
            
            # 获取今日价格
            df_today = pd.read_sql_query(
                f"SELECT 收盘 FROM etf_{code} WHERE 日期 = '2025-12-22' LIMIT 1",
                etf_conn
            )
            if df_today.empty:
                df_today = pd.read_sql_query(
                    f"SELECT close FROM etf_{code} WHERE date = '2025-12-22' LIMIT 1",
                    etf_conn
                )
            
            if not df_yesterday.empty and not df_today.empty:
                price_yesterday = float(df_yesterday.iloc[0].iloc[0])
                price_today = float(df_today.iloc[0].iloc[0])
                
                value_yesterday = qty * price_yesterday
                value_today = qty * price_today
                
                total_yesterday_value += value_yesterday
                total_today_value += value_today
                
                change = price_today - price_yesterday
                change_pct = (change / price_yesterday) * 100
                
                print(f"{code}:")
                print(f"  持仓: {qty:.2f}")
                print(f"  昨日价格: {price_yesterday:.3f} → 今日价格: {price_today:.3f}")
                print(f"  价格变化: {change:+.3f} ({change_pct:+.2f}%)")
                print(f"  市值变化: {value_yesterday:.2f} → {value_today:.2f} ({value_today-value_yesterday:+.2f})")
                print()
                
        except Exception as e:
            print(f"{code}: 无法获取价格 ({e})")

etf_conn.close()

print(f"持仓总市值变化: {total_yesterday_value:.2f} → {total_today_value:.2f}")
print(f"持仓贡献: {total_today_value - total_yesterday_value:+.2f}")

# 获取现金
last_cash = pd.read_sql_query(
    "SELECT capital_after FROM trades ORDER BY date DESC LIMIT 1",
    sqlite3.connect('data/trade_history.db')
).iloc[0]['capital_after']

print(f"\n现金（未变）: {last_cash:.2f}")
print(f"\n理论今日净值: {last_cash + total_today_value:.2f}")
print(f"实际今日净值: {today_equity:.2f}")
print(f"差异: {abs(today_equity - (last_cash + total_today_value)):.2f}")

print("\n=== 分析完成 ===")

