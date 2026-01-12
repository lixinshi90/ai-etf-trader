# -*- coding: utf-8 -*-
"""
Backfill daily_equity rows for KPI computation without touching trades.

Usage examples (run in project root):
  # Backfill yesterday with latest equity; baseline = day before yesterday = INITIAL_CAPITAL
  python -m scripts.backfill_yyyymmdd --yesterday

  # Backfill a specific date with given equity, baseline auto = date-1 with INITIAL_CAPITAL
  python -m scripts.backfill_yyyymmdd --as 2025-12-04 --equity 102345.67

  # Only set baseline (no as-date), e.g. 2025-12-03 = INITIAL_CAPITAL
  python -m scripts.backfill_yyyymmdd --baseline 2025-12-03

Notes:
- Reads INITIAL_CAPITAL from .env (default 100000)
- Upsert logic: insert if not exists, update if exists
- Database: data/trade_history.db
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
from dotenv import load_dotenv


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def db_path() -> str:
    return os.path.join(project_root(), "data", "trade_history.db")


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")


def upsert(conn: sqlite3.Connection, date_str: str, equity: float) -> None:
    cur = conn.execute("SELECT 1 FROM daily_equity WHERE date=?", (date_str,))
    if cur.fetchone():
        conn.execute("UPDATE daily_equity SET equity=? WHERE date=?", (float(equity), date_str))
    else:
        conn.execute("INSERT INTO daily_equity(date, equity) VALUES(?, ?)", (date_str, float(equity)))


def latest_equity(conn: sqlite3.Connection, init_capital: float) -> float:
    # Prefer last in daily_equity, fallback to last capital_after in trades
    try:
        deq = pd.read_sql_query("SELECT date, equity FROM daily_equity ORDER BY date", conn)
        if not deq.empty:
            return float(deq["equity"].iloc[-1])
    except Exception:
        pass
    try:
        tr = pd.read_sql_query("SELECT capital_after FROM trades ORDER BY datetime(date)", conn)
        if not tr.empty and tr["capital_after"].notna().any():
            return float(tr["capital_after"].dropna().iloc[-1])
    except Exception:
        pass
    return float(init_capital)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill daily_equity for KPI")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--yesterday", action="store_true", help="Backfill yesterday using latest equity")
    g.add_argument("--as", dest="as_date", type=str, help="Backfill a specific date YYYY-MM-DD")
    p.add_argument("--equity", type=float, default=None, help="Equity to set for --as date; default: latest")
    p.add_argument("--baseline", type=str, default=None, help="Baseline date YYYY-MM-DD (set to INITIAL_CAPITAL)")
    return p.parse_args()


def main() -> None:
    load_dotenv(override=True)
    init_cap = float(os.getenv("INITIAL_CAPITAL", "100000"))
    args = parse_args()

    today = datetime.now().date()
    if args.yesterday:
        as_date = today - timedelta(days=1)
        baseline = as_date - timedelta(days=1)
    else:
        as_date = None
        if args.as_date:
            as_date = datetime.strptime(args.as_date, "%Y-%m-%d").date()
        baseline = None
        if args.baseline:
            baseline = datetime.strptime(args.baseline, "%Y-%m-%d").date()
        elif as_date is not None:
            baseline = as_date - timedelta(days=1)

    fp = db_path()
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    conn = sqlite3.connect(fp)
    try:
        ensure_table(conn)
        # Baseline first
        if baseline is not None:
            upsert(conn, baseline.strftime("%Y-%m-%d"), init_cap)
            print(f"[backfill] baseline set {baseline} = {init_cap:.2f}")
        # as-date
        if as_date is not None:
            eq = args.equity
            if eq is None:
                eq = latest_equity(conn, init_cap)
            upsert(conn, as_date.strftime("%Y-%m-%d"), float(eq))
            print(f"[backfill] as-date set {as_date} = {float(eq):.2f}")
        conn.commit()
        print(f"[backfill] done -> {fp}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

