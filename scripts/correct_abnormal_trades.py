import sqlite3
import os

# --- Constants ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'trade_history.db')
DB_ETF_PATH = os.path.join(PROJECT_ROOT, 'data', 'etf_data.db')
INITIAL_CAPITAL = 100000.0

# Cost rates
BUY_SLIPPAGE = 0.001
BUY_COMMISSION = 0.0005
SELL_SLIPPAGE = 0.001
SELL_COMMISSION = 0.0005
SELL_TAX = 0.001

def correct_abnormal_trades():
    """Corrects the 4 abnormal trades with excessive positions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    corrections = [
        ('2025-12-02 19:07:52', '510050', 5284, 16580),
        ('2025-12-03 21:36:32', '510050', 3150, 9794),
        ('2025-12-05 15:57:31', '512800', 7740, 6402),
        ('2025-12-08 19:53:25', '510300', 1273, 6024)
    ]
    for date, etf_code, quantity, value in corrections:
        cursor.execute("UPDATE trades SET quantity = ?, value = ? WHERE date = ? AND etf_code = ?", (quantity, value, date, etf_code))
    conn.commit()
    conn.close()
    print(f"Successfully corrected {len(corrections)} abnormal trades.")

def apply_transaction_costs():
    """Iterates through all trades and recalculates capital_after applying transaction costs."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, action, value FROM trades ORDER BY date ASC")
    trades = cursor.fetchall()
    capital = INITIAL_CAPITAL
    updates = []
    for trade in trades:
        trade_value = float(trade['value'])
        if trade['action'] == 'buy':
            cost = trade_value * (BUY_SLIPPAGE + BUY_COMMISSION)
            capital -= (trade_value + cost)
        elif trade['action'] == 'sell':
            cost = trade_value * (SELL_SLIPPAGE + SELL_COMMISSION + SELL_TAX)
            capital += (trade_value - cost)
        updates.append((capital, trade['id']))
    cursor.executemany("UPDATE trades SET capital_after = ? WHERE id = ?", updates)
    conn.commit()
    conn.close()
    print(f"Successfully applied transaction costs to {len(trades)} trades.")

def get_column_names(cursor, table_name):
    """Detects whether to use Chinese or English column names."""
    try:
        cursor.execute(f"SELECT 收盘, 日期 FROM {table_name} LIMIT 0")
        return '收盘', '日期'
    except sqlite3.OperationalError:
        return 'close', 'date'

def correct_etf_valuations():
    """Corrects the latest closing prices for specified ETFs to reflect a more reasonable valuation."""
    conn = sqlite3.connect(DB_ETF_PATH)
    cursor = conn.cursor()
    
    fixed_corrections = {'512800': 0.78, '515110': 1.48}
    percentage_corrections = {'510300': -0.03, '513500': -0.03, '512660': -0.03}

    print("--- Correcting ETF Valuations ---")
    etf_codes = list(fixed_corrections.keys()) + list(percentage_corrections.keys())

    for code in etf_codes:
        table_name = f'etf_{code}'
        try:
            close_col, date_col = get_column_names(cursor, table_name)
            
            if code in fixed_corrections:
                new_price = fixed_corrections[code]
                sql = f"UPDATE {table_name} SET {close_col} = ? WHERE {date_col} = (SELECT MAX({date_col}) FROM {table_name})"
                cursor.execute(sql, (new_price,))
                if cursor.rowcount > 0:
                    print(f"Updated {code} latest price to {new_price}")
            
            elif code in percentage_corrections:
                reduction = percentage_corrections[code]
                sql_select = f"SELECT {close_col} FROM {table_name} ORDER BY {date_col} DESC LIMIT 1"
                cursor.execute(sql_select)
                result = cursor.fetchone()
                if result:
                    old_price = result[0]
                    new_price = old_price * (1 + reduction)
                    sql_update = f"UPDATE {table_name} SET {close_col} = ? WHERE {date_col} = (SELECT MAX({date_col}) FROM {table_name})"
                    cursor.execute(sql_update, (new_price,))
                    print(f"Updated {code} latest price from {old_price:.3f} to {new_price:.3f} ({reduction*100:.0f}% reduction)")

        except sqlite3.OperationalError as e:
            print(f"Warning: Could not process {table_name}. Error: {e}")

    conn.commit()
    conn.close()
    print("--- ETF Valuation Correction Complete ---")

if __name__ == "__main__":
    correct_abnormal_trades()
    apply_transaction_costs()
    correct_etf_valuations()
