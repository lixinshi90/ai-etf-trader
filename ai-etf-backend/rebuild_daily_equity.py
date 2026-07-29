# -*- coding: utf-8 -*-
"""
重构 daily_equity 表，统一使用累加方法
"""
import sys
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 重构 daily_equity 表 ===\n")

conn = sqlite3.connect('data/trade_history.db')
etf_conn = sqlite3.connect('data/etf_data.db')

# 备份原始数据
print("1. 备份原始 daily_equity 表...", end=' ')
df_original = pd.read_sql_query("SELECT * FROM daily_equity", conn)
df_original.to_sql('daily_equity_backup', conn, if_exists='replace', index=False)
print(f"✓ {len(df_original)} 条记录已备份到 daily_equity_backup\n")

# 获取所有交易日
dates = sorted(df_original['date'].unique())
print(f"2. 共有 {len(dates)} 个交易日需要重新计算\n")

# 初始资金
initial_capital = 100000.0

new_equity_data = []

for date in dates:
    # 1. 计算累加现金
    df_trades = pd.read_sql_query(
        f"SELECT action, value FROM trades WHERE date <= '{date} 23:59:59' ORDER BY date",
        conn
    )
    
    cash = initial_capital
    for _, t in df_trades.iterrows():
        action = str(t['action']).lower()
        value = float(t['value'])
        if action == 'buy':
            cash -= value
        elif action == 'sell':
            cash += value
    
    # 2. 计算持仓市值
    df_holdings = pd.read_sql_query(
        f"SELECT etf_code, action, quantity FROM trades WHERE date <= '{date} 23:59:59' ORDER BY date",
        conn
    )
    
    holdings = {}
    for _, h in df_holdings.iterrows():
        code = str(h['etf_code']).strip()
        if code:
            qty = float(h['quantity'])
            if str(h['action']).lower() == 'sell':
                qty = -qty
            holdings[code] = holdings.get(code, 0.0) + qty
    
    holdings_value = 0
    for code, qty in holdings.items():
        if qty > 0.001:
            try:
                df_p = pd.read_sql_query(
                    f"SELECT 收盘 FROM etf_{code} WHERE 日期 <= '{date}' ORDER BY 日期 DESC LIMIT 1",
                    etf_conn
                )
                if df_p.empty:
                    df_p = pd.read_sql_query(
                        f"SELECT close FROM etf_{code} WHERE date <= '{date}' ORDER BY date DESC LIMIT 1",
                        etf_conn
                    )
                
                if not df_p.empty:
                    price = float(df_p.iloc[0].iloc[0])
                    holdings_value += qty * price
            except:
                pass
    
    # 理论总资产
    new_equity = cash + holdings_value
    new_equity_data.append({'date': date, 'new_equity': new_equity})

df_new = pd.DataFrame(new_equity_data)
df_merged = pd.merge(df_original, df_new, on='date')

print("3. 新旧数据对比:\n")
print("      日期      |  旧净值  |  新净值  |   差异   | 差异率")
print("----------------|----------|----------|----------|---------")

for _, row in df_merged.iterrows():
    date = row['date']
    old_val = row['equity']
    new_val = row['new_equity']
    diff = new_val - old_val
    diff_pct = (diff / old_val) * 100 if old_val > 0 else 0
    
    print(f"{date} | {old_val:8.2f} | {new_val:8.2f} | {diff:8.2f} | {diff_pct:6.2f}%")

print("\n4. 确认更新数据库？(y/n): ", end='')
response = input()

if response.lower() == 'y':
    cursor = conn.cursor()
    for _, row in df_merged.iterrows():
        cursor.execute(
            "UPDATE daily_equity SET equity = ? WHERE date = ?",
            (row['new_equity'], row['date'])
        )
    conn.commit()
    print(f"\n✓ 已更新 {len(df_merged)} 条记录")
else:
    print("\n取消更新")

etf_conn.close()
conn.close()

print("\n=== 完成 ===")

