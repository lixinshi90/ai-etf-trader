#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3
import pandas as pd
import sys

try:
    conn = sqlite3.connect('data/trade_history.db')
    
    # 查询2025-12-11和2025-12-12的交易
    query = """
    SELECT date, etf_code, action, price, quantity, value, capital_after 
    FROM trades 
    WHERE date >= '2025-12-11' 
    ORDER BY date
    """
    
    df = pd.read_sql_query(query, conn)
    
    if len(df) == 0:
        print("No trades found for 2025-12-11 and 2025-12-12")
    else:
        print("=" * 150)
        print("TRADES FROM 2025-12-11 TO 2025-12-12")
        print("=" * 150)
        for idx, row in df.iterrows():
            print(f"{row['date']} | {row['etf_code']:6s} | {row['action']:4s} | px={row['price']:8.4f} | qty={row['quantity']:12.4f} | val={row['value']:12.2f} | cash_after={row['capital_after']:12.2f}")
        
        print("\n" + "=" * 150)
        print("SUMMARY")
        print("=" * 150)
        
        # 按日期分组统计
        df['date_only'] = df['date'].str.split(' ').str[0]
        for date in df['date_only'].unique():
            day_df = df[df['date_only'] == date]
            buys = day_df[day_df['action'] == 'buy']
            sells = day_df[day_df['action'] == 'sell']
            
            buy_value = buys['value'].sum() if len(buys) > 0 else 0
            sell_value = sells['value'].sum() if len(sells) > 0 else 0
            
            print(f"\n{date}:")
            print(f"  Buy trades: {len(buys)}, Total value: {buy_value:,.2f}")
            print(f"  Sell trades: {len(sells)}, Total value: {sell_value:,.2f}")
            if len(day_df) > 0:
                final_cash = day_df.iloc[-1]['capital_after']
                print(f"  Final cash: {final_cash:,.2f}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()


