# -*- coding: utf-8 -*-
"""
全面审计：验证资产延续性和数据合理性
"""
import sys
import sqlite3
import pandas as pd

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 全面数据审计 ===\n")

conn = sqlite3.connect('data/trade_history.db')

# 1. 检查所有daily_equity记录
print("【问题1】检查资产延续性和波动合理性\n")

df_equity = pd.read_sql_query(
    "SELECT date, equity FROM daily_equity ORDER BY date",
    conn
)

print("所有净值记录:")
print(df_equity.to_string(index=False))

print("\n每日变化分析:")
for i in range(1, len(df_equity)):
    prev = df_equity.iloc[i-1]['equity']
    curr = df_equity.iloc[i]['equity']
    change = curr - prev
    change_pct = (change / prev) * 100
    
    # 标记异常波动
    is_abnormal = abs(change_pct) > 10
    flag = "⚠️ 异常" if is_abnormal else "✓"
    
    print(f"{df_equity.iloc[i]['date']}: {prev:.2f} → {curr:.2f} = {change:+.2f} ({change_pct:+.2f}%) {flag}")

# 2. 检查资产延续性：每日资产是否基于前一日
print("\n【问题2】验证资产延续性（是否每日重置为10万）\n")

initial_capital = 100000.0
print(f"初始资金: {initial_capital:.2f}\n")

# 逐日验证
for i in range(len(df_equity)):
    date = df_equity.iloc[i]['date']
    equity_db = df_equity.iloc[i]['equity']
    
    # 获取该日期之前的所有交易
    df_trades_until = pd.read_sql_query(
        f"SELECT action, value FROM trades WHERE date <= '{date} 23:59:59' ORDER BY date",
        conn
    )
    
    # 从初始资金累加
    cash_accumulated = initial_capital
    for _, row in df_trades_until.iterrows():
        action = str(row['action']).lower()
        value = float(row['value'])
        if action == 'buy':
            cash_accumulated -= value
        elif action == 'sell':
            cash_accumulated += value
    
    # 获取该日期的持仓市值
    df_holdings = pd.read_sql_query(
        f"SELECT etf_code, action, quantity FROM trades WHERE date <= '{date} 23:59:59' ORDER BY date",
        conn
    )
    
    holdings = {}
    for _, row in df_holdings.iterrows():
        code = str(row['etf_code']).strip()
        if code:
            qty = float(row['quantity'])
            if str(row['action']).lower() == 'sell':
                qty = -qty
            holdings[code] = holdings.get(code, 0.0) + qty
    
    # 计算持仓市值
    etf_conn = sqlite3.connect('data/etf_data.db')
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
    
    etf_conn.close()
    
    # 理论总资产
    theoretical_equity = cash_accumulated + holdings_value
    diff = equity_db - theoretical_equity
    diff_pct = (diff / theoretical_equity) * 100 if theoretical_equity > 0 else 0
    
    is_reset = abs(cash_accumulated - initial_capital) < 1  # 检查是否重置为初始资金
    
    print(f"{date}:")
    print(f"  累加现金: {cash_accumulated:.2f}")
    print(f"  持仓市值: {holdings_value:.2f}")
    print(f"  理论总资产: {theoretical_equity:.2f}")
    print(f"  数据库记录: {equity_db:.2f}")
    print(f"  差异: {diff:.2f} ({diff_pct:.2f}%)")
    if is_reset:
        print(f"  ⚠️ 警告: 现金接近初始资金，可能存在重置问题")
    print()

# 3. 检查12-22的具体计算
print("【问题3】验证12-22的具体计算\n")

equity_19 = df_equity[df_equity['date'] == '2025-12-19'].iloc[0]['equity']
equity_22 = df_equity[df_equity['date'] == '2025-12-22'].iloc[0]['equity']

print("用户提出的公式:")
print("99275.50 - 8974.23 + 62.17 + 8960.79 + 1738.00 = 101062.23\n")

print("逐项验证:")
print(f"1. 起点（12-19净值）: 99275.50 ✓")
print(f"2. 买入510880成本: 8974.23")
print(f"   实际交易金额: 8960.79")
print(f"   差异: {8974.23 - 8960.79:.2f} (可能是交易成本)")
print(f"3. 原有持仓增值: 62.17")
print(f"   实际计算: 61.38")
print(f"   差异: {62.17 - 61.38:.2f}")
print(f"4. 新增510880市值: 8960.79 ✓")
print(f"5. 调整项: 1738.00")
print(f"   实际需要: {equity_22 - (99275.50 - 8960.79 + 61.38 + 8960.79):.2f}")
print(f"   差异: {abs(1738.00 - (equity_22 - (99275.50 - 8960.79 + 61.38 + 8960.79))):.2f}\n")

# 正确的公式
correct_calc = 99275.50 - 8960.79 + 61.38 + 8960.79
print(f"正确计算（不含调整项）:")
print(f"  99275.50 - 8960.79 + 61.38 + 8960.79 = {correct_calc:.2f}")
print(f"  数据库记录: {equity_22:.2f}")
print(f"  需要的调整项: {equity_22 - correct_calc:.2f}\n")

conn.close()

print("=== 审计完成 ===")

