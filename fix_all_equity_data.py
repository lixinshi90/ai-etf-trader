# -*- coding: utf-8 -*-
"""
修正所有净值数据，使用累加方法重新计算
"""
import sys
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 修正所有净值数据 ===\n")

conn = sqlite3.connect('data/trade_history.db')
etf_conn = sqlite3.connect('data/etf_data.db')

# 获取所有需要修正的日期
df_equity = pd.read_sql_query(
    "SELECT date, equity FROM daily_equity ORDER BY date",
    conn
)

print(f"共有 {len(df_equity)} 天的净值记录\n")

# 初始资金
initial_capital = 100000.0

corrections = []

for _, row in df_equity.iterrows():
    date = row['date']
    equity_db = row['equity']
    
    # 计算该日期的理论净值
    # 1. 累加现金
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
    theoretical_equity = cash + holdings_value
    diff = equity_db - theoretical_equity
    diff_pct = (diff / theoretical_equity) * 100 if theoretical_equity > 0 else 0
    
    # 如果差异超过1%，记录需要修正
    if abs(diff_pct) > 1.0:
        corrections.append({
            'date': date,
            'old_equity': equity_db,
            'new_equity': theoretical_equity,
            'diff': diff,
            'diff_pct': diff_pct
        })
    
    status = "⚠️ 需修正" if abs(diff_pct) > 1.0 else "✓"
    print(f"{date}: {equity_db:.2f} → {theoretical_equity:.2f} (差异: {diff:+.2f}, {diff_pct:+.2f}%) {status}")

etf_conn.close()

print(f"\n需要修正的记录: {len(corrections)} 条\n")

if corrections:
    print("修正明细:")
    for c in corrections:
        print(f"  {c['date']}: {c['old_equity']:.2f} → {c['new_equity']:.2f} ({c['diff']:+.2f}, {c['diff_pct']:+.2f}%)")
    
    print(f"\n确认修正这 {len(corrections)} 条记录？(y/n): ", end='')
    response = input()
    
    if response.lower() == 'y':
        cursor = conn.cursor()
        for c in corrections:
            cursor.execute(
                "UPDATE daily_equity SET equity = ? WHERE date = ?",
                (c['new_equity'], c['date'])
            )
        conn.commit()
        print(f"\n✓ 已修正 {len(corrections)} 条记录")
    else:
        print("\n取消修正")
else:
    print("✓ 所有数据都在合理范围内，无需修正")

conn.close()

print("\n=== 完成 ===")

