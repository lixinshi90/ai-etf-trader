# -*- coding: utf-8 -*-
"""Track daily portfolio PnL and append to a history CSV.

- Called automatically at the end of daily_once.py.
- Appends a snapshot of each position's PnL for the current day.

Output CSV: out/pnl_tracker_history.csv
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import sqlite3
from datetime import datetime

import pandas as pd


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    root = project_root()
    trade_db_path = os.path.join(root, "data", "trade_history.db")
    etf_db_path = os.path.join(root, "data", "etf_data.db")
    output_csv_path = os.path.join(root, "out", "pnl_tracker_history.csv")

    if not os.path.exists(trade_db_path) or not os.path.exists(etf_db_path):
        print("[track_pnl] DB not found, skipping.")
        return

    try:
        from src.trade_executor import TradeExecutor
    except ImportError:
        print("[track_pnl] Could not import TradeExecutor, skipping.")
        return

    executor = TradeExecutor(initial_capital=0.0, db_path=trade_db_path)
    executor.restore_state_from_db()

    positions = executor.positions
    if not positions:
        return

    etf_conn = sqlite3.connect(etf_db_path)
    pnl_rows = []
    snapshot_date = datetime.now().strftime("%Y-%m-%d")

    try:
        for code, pos_data in positions.items():
            qty = float(pos_data.get("quantity", 0.0))
            entry_price = float(pos_data.get("entry_price", 0.0))
            if qty <= 1e-9 or entry_price <= 0:
                continue

            latest_close = None
            try:
                row = etf_conn.execute(
                    f"SELECT 收盘 FROM etf_{code} ORDER BY 日期 DESC LIMIT 1"
                ).fetchone()
                if row and row[0] is not None:
                    latest_close = float(row[0])
            except sqlite3.OperationalError:
                try:
                    row = etf_conn.execute(
                        f"SELECT close FROM etf_{code} ORDER BY date DESC LIMIT 1"
                    ).fetchone()
                    if row and row[0] is not None:
                        latest_close = float(row[0])
                except Exception:
                    pass
            
            if latest_close is None:
                continue

            market_value = qty * latest_close
            cost_basis = qty * entry_price
            pnl_value = market_value - cost_basis
            pnl_pct = (pnl_value / cost_basis) * 100.0 if cost_basis > 0 else 0.0

            pnl_rows.append({
                "snapshot_date": snapshot_date,
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
        return

    df = pd.DataFrame(pnl_rows)

    # Append to CSV
    file_exists = os.path.exists(output_csv_path)
    df.to_csv(output_csv_path, mode='a', header=not file_exists, index=False, encoding='utf-8-sig')
    print(f"[track_pnl] Appended {len(df)} rows to {output_csv_path}")


if __name__ == "__main__":
    main()

