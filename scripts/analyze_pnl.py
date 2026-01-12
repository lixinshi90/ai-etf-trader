# -*- coding: utf-8 -*-
"""Analyze current portfolio's floating Profit and Loss (PnL).

- Reconstructs current positions from trade_history.db using full replay.
- Fetches latest close prices from etf_data.db.
- Calculates and prints PnL for each position, sorted by loss.

Usage:
  uv run python scripts/analyze_pnl.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import sqlite3
from typing import Dict

import pandas as pd


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    root = project_root()
    trade_db_path = os.path.join(root, "data", "trade_history.db")
    etf_db_path = os.path.join(root, "data", "etf_data.db")

    if not os.path.exists(trade_db_path):
        raise SystemExit(f"Trade DB not found: {trade_db_path}")
    if not os.path.exists(etf_db_path):
        raise SystemExit(f"ETF DB not found: {etf_db_path}")

    # Use a temporary, in-memory TradeExecutor to reuse its restore logic
    # This ensures the logic is identical to the main daily task
    try:
        from src.trade_executor import TradeExecutor
    except ImportError:
        raise SystemExit("Could not import TradeExecutor from src.")

    # We don't need initial capital here as we are restoring from a real history
    executor = TradeExecutor(initial_capital=0.0, db_path=trade_db_path)
    executor.restore_state_from_db()

    positions = executor.positions
    if not positions:
        print("No current positions found.")
        return

    etf_conn = sqlite3.connect(etf_db_path)
    pnl_rows = []

    total_market_value = 0.0

    try:
        for code, pos_data in positions.items():
            qty = float(pos_data.get("quantity", 0.0))
            entry_price = float(pos_data.get("entry_price", 0.0))
            if qty <= 1e-9 or entry_price <= 0:
                continue

            # Fetch latest close price
            latest_close = None
            try:
                # Try Chinese schema
                row = etf_conn.execute(
                    f"SELECT 收盘 FROM etf_{code} ORDER BY 日期 DESC LIMIT 1"
                ).fetchone()
                if row and row[0] is not None:
                    latest_close = float(row[0])
            except sqlite3.OperationalError:
                try:
                    # Fallback to English schema
                    row = etf_conn.execute(
                        f"SELECT close FROM etf_{code} ORDER BY date DESC LIMIT 1"
                    ).fetchone()
                    if row and row[0] is not None:
                        latest_close = float(row[0])
                except Exception:
                    pass # No price found
            
            if latest_close is None:
                pnl_rows.append({
                    "etf_code": code,
                    "quantity": qty,
                    "avg_cost": entry_price,
                    "latest_price": "N/A",
                    "market_value": "N/A",
                    "pnl_value": "N/A",
                    "pnl_pct": "N/A",
                })
                continue

            market_value = qty * latest_close
            cost_basis = qty * entry_price
            pnl_value = market_value - cost_basis
            pnl_pct = (pnl_value / cost_basis) * 100.0 if cost_basis > 0 else 0.0

            total_market_value += market_value

            pnl_rows.append({
                "etf_code": code,
                "quantity": qty,
                "avg_cost": entry_price,
                "latest_price": latest_close,
                "market_value": market_value,
                "pnl_value": pnl_value,
                "pnl_pct": pnl_pct,
            })

    finally:
        etf_conn.close()

    if not pnl_rows:
        print("Could not calculate PnL for any positions.")
        return

    df = pd.DataFrame(pnl_rows)
    df = df.sort_values(by="pnl_value", ascending=True)

    # Calculate PnL contribution to total portfolio
    total_equity = executor.capital + total_market_value
    df["pnl_contr_pct"] = df["pnl_value"].apply(lambda x: (x / total_equity) * 100.0 if total_equity > 0 and isinstance(x, (int, float)) else 0.0)

    pd.set_option('display.float_format', lambda x: f'{x:,.2f}')
    print("=== Current Portfolio Floating PnL ===")
    print(f"- As of latest market data")
    print(f"- Cash: {executor.capital:,.2f}")
    print(f"- Holdings Value: {total_market_value:,.2f}")
    print(f"- Total Equity: {total_equity:,.2f}")
    print("-" * 40)

    # Reorder columns for display
    display_cols = ["etf_code", "pnl_value", "pnl_pct", "pnl_contr_pct", "market_value", "quantity", "avg_cost", "latest_price"]
    print(df[display_cols].to_string(index=False))


if __name__ == "__main__":
    main()

