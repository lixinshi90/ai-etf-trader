# -*- coding: utf-8 -*-
"""
One-off script to realize partial profits from existing high-profit positions.

Usage:
  uv run python scripts/partial_sell.py

This script will:
1. Load the current positions from the trade history.
2. For a predefined list of tickers, sell a specified ratio of the position.
3. Use the live price from akshare to execute the sale.
4. Record the sell trades in the database, effectively reducing the position size
   and increasing the cash balance.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

# Ensure the src path is in the sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.trade_executor import TradeExecutor
from src.data_fetcher import ak

def get_current_price(etf_code: str) -> float | None:
    """Fetches the current price for a given ETF code."""
    if ak is None:
        print(f"Error: akshare is not installed.")
        return None
    try:
        # Try Eastmoney first
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty:
            price = df[df['代码'] == etf_code]['最新价'].iloc[0]
            if price > 0:
                return float(price)
    except Exception:
        pass # Fallback to THS
    
    try:
        # Fallback to THS
        df = ak.fund_etf_spot_ths()
        if df is not None and not df.empty:
            price = df[df['基金代码'] == etf_code]['最新-单位净值'].iloc[0]
            if price > 0:
                return float(price)
    except Exception:
        pass

    print(f"Warning: Could not fetch live price for {etf_code}. Cannot execute sell.")
    return None

def main():
    # --- Configuration ---
    # Define which ETFs to sell and what ratio of the position to sell
    sell_plan = {
        "512800": 0.5,  # Sell 50% of the position
        "515110": 0.4,  # Sell 40% of the position
        "516160": 0.3,  # Sell 30% of the position
    }

    print("--- Starting Partial Profit Realization ---")

    # Initialize the executor, which will load the current state from the DB
    executor = TradeExecutor()
    executor.restore_state_from_db()

    print(f"Initial state: Cash = {executor.capital:.2f}, Positions = {list(executor.positions.keys())}")

    # Create a dictionary of all current prices
    all_codes = list(executor.positions.keys())
    current_prices = {code: get_current_price(code) for code in all_codes}

    # Execute the sell plan
    for etf_code, sell_ratio in sell_plan.items():
        if etf_code in executor.positions:
            current_price = current_prices.get(etf_code)
            if current_price:
                # The execute_trade method now handles partial sells via `sell_ratio` in the decision dict
                decision = {
                    "decision": "sell",
                    "sell_ratio": sell_ratio,
                    "confidence": 0.9,
                    "reasoning": "主动兑现部分浮盈，平衡买卖比例"
                }
                executor.execute_trade(etf_code, decision, current_price, current_prices)
                print(f"Executed partial sell for {etf_code}: {sell_ratio*100}% of the position.")
            else:
                print(f"Skipping {etf_code}: Could not fetch current price.")
        else:
            print(f"Skipping {etf_code}: Not in current positions.")

    # Final state
    final_value = executor.get_portfolio_value(current_prices)
    print("\n--- Partial Sell Complete ---")
    print(f"Final state: Cash = {executor.capital:.2f}, Holdings Value = {final_value - executor.capital:.2f}, Total Value = {final_value:.2f}")

if __name__ == "__main__":
    main()

