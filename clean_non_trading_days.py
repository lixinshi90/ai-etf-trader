# -*- coding: utf-8 -*-
"""
清理数据库中的非交易日数据
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

DB_PATH = 'data/trade_history.db'

def get_trading_days():
    """获取A股交易日列表（使用akshare）"""
    try:
        import akshare as ak
        trade_cal = ak.tool_trade_date_hist_sina()
        trading_days = set(pd.to_datetime(trade_cal['trade_date']).dt.strftime('%Y-%m-%d'))
        return trading_days
    except Exception as e:
        print(f"Warning: Could not fetch trading calendar: {e}")
        # Fallback: assume weekdays are trading days
        start = datetime(2025, 11, 26)
        end = datetime(2025, 12, 22)
        trading_days = set()
        current = start
        while current <= end:
            if current.weekday() < 5:  # Monday-Friday
                trading_days.add(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        return trading_days

def clean_database():
    """清理数据库中的非交易日数据"""
    trading_days = get_trading_days()
    print(f"Trading days in range: {len(trading_days)}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Check daily_equity
    df_equity = pd.read_sql_query("SELECT date, equity FROM daily_equity ORDER BY date", conn)
    print(f"\n=== Daily Equity ===")
    print(f"Total records: {len(df_equity)}")
    
    non_trading = df_equity[~df_equity['date'].isin(trading_days)]
    if len(non_trading) > 0:
        print(f"Non-trading day records found: {len(non_trading)}")
        print(non_trading)
        
        # Delete non-trading days
        for date in non_trading['date']:
            cursor.execute("DELETE FROM daily_equity WHERE date = ?", (date,))
        print(f"Deleted {len(non_trading)} non-trading day records from daily_equity")
    else:
        print("No non-trading day records in daily_equity")
    
    # 2. Check trades
    df_trades = pd.read_sql_query("SELECT date, etf_code, action FROM trades ORDER BY date", conn)
    print(f"\n=== Trades ===")
    print(f"Total records: {len(df_trades)}")
    
    if len(df_trades) > 0:
        df_trades['date_only'] = pd.to_datetime(df_trades['date']).dt.strftime('%Y-%m-%d')
        non_trading_trades = df_trades[~df_trades['date_only'].isin(trading_days)]
        
        if len(non_trading_trades) > 0:
            print(f"Non-trading day trades found: {len(non_trading_trades)}")
            print(non_trading_trades[['date', 'etf_code', 'action']])
            
            # Delete non-trading day trades
            for date in non_trading_trades['date'].unique():
                cursor.execute("DELETE FROM trades WHERE date LIKE ?", (f"{date[:10]}%",))
            print(f"Deleted {len(non_trading_trades)} non-trading day records from trades")
        else:
            print("No non-trading day records in trades")
    
    conn.commit()
    conn.close()
    
    print("\n=== Cleanup Complete ===")

if __name__ == '__main__':
    clean_database()

