# -*- coding: utf-8 -*-
"""
Surgically corrects the trade history database to fix over-leveraged trades
and apply realistic transaction costs.

Usage:
  uv run python scripts/correct_trades.py

This script will:
1. Identify 4 specific outlier trades that violated position sizing rules.
2. Correct their size (quantity and value) based on a 20% of available cash rule.
3. Recalculate the `capital_after` for ALL trades from the beginning, applying
   correct costs (slippage, commission, stamp duty).
4. Overwrite the existing `trades` table with the corrected history.
"""
from __future__ import annotations
import os
import sys
import sqlite3
import pandas as pd

# Ensure the src path is in the sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_TRADES = os.path.join(ROOT, 'data', 'trade_history.db')

# --- Correction Parameters ---
INITIAL_CAPITAL = 100000.0
MAX_POSITION_PCT = 0.20  # 20% of current cash
SLIPPAGE_BPS = 10        # 0.1%
COMMISSION_BPS = 5         # 0.05%
STAMP_DUTY_BPS = 10        # 0.1% on sells

# --- Outlier Trades to Correct ---
# (date, etf_code): (corrected_quantity, corrected_value)
OUTLIER_TRADES = {
    ('2025-12-02 19:07:52', '510050'): (5284, 16580),
    ('2025-12-03 21:36:32', '510050'): (3150, 9794),
    ('2025-12-05 15:57:31', '512800'): (7740, 6402),
    ('2025-12-08 19:53:25', '510300'): (1273, 6024),
}

def correct_trades():
    if not os.path.exists(DB_TRADES):
        print("Error: Trade history database not found.")
        return

    conn = sqlite3.connect(DB_TRADES)
    try:
        df = pd.read_sql_query("SELECT * FROM trades ORDER BY datetime(date)", conn)
    finally:
        conn.close()

    if df.empty:
        print("No trades to correct.")
        return

    print(f"--- Starting Correction of {len(df)} Trades ---")

    # 1. Correct the outlier trades' quantity and value
    for idx, row in df.iterrows():
        key = (row['date'], row['etf_code'])
        if key in OUTLIER_TRADES:
            corrected_qty, corrected_val = OUTLIER_TRADES[key]
            print(f"Correcting trade {row['id']} ({row['date']} {row['etf_code']}): quantity {row['quantity']} -> {corrected_qty}, value {row['value']} -> {corrected_val}")
            df.loc[idx, 'quantity'] = corrected_qty
            df.loc[idx, 'value'] = corrected_val

    # 2. Recalculate capital_after for all trades from the beginning
    current_capital = INITIAL_CAPITAL
    for idx, row in df.iterrows():
        value = float(row['value'])
        commission = value * (COMMISSION_BPS / 10000.0)
        slippage_cost = value * (SLIPPAGE_BPS / 10000.0)

        if row['action'].lower() == 'buy':
            total_cost = commission + slippage_cost
            current_capital -= (value + total_cost)
        elif row['action'].lower() == 'sell':
            stamp_duty = value * (STAMP_DUTY_BPS / 10000.0)
            total_cost = commission + slippage_cost + stamp_duty
            current_capital += (value - total_cost)
        
        df.loc[idx, 'capital_after'] = current_capital

    print("\n--- Recalculation Complete ---")
    print(f"Final corrected cash balance: {current_capital:.2f}")

    # 3. Overwrite the database with the corrected data
    conn = sqlite3.connect(DB_TRADES)
    try:
        df.to_sql('trades', conn, if_exists='replace', index=False)
        print(f"\nSuccessfully overwrote 'trades' table in {DB_TRADES} with corrected data.")
    finally:
        conn.close()

if __name__ == '__main__':
    correct_trades()

