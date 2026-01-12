# -*- coding: utf-8 -*-
"""Check missing daily_equity snapshots on inferred trading days.

口径 B：用数据库里 etf_XXXXXX 日线表的日期并集推断“实际交易日”，
然后检查 daily_equity 是否对这些交易日都有净值快照。

Usage:
  uv run python scripts/check_missing_equity_days.py --start 2025-11-27

Outputs:
  - prints summary
  - writes out/missing_equity_days_<start>_to_<end>.csv
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from typing import Iterable

import pandas as pd


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def list_etf_tables(conn: sqlite3.Connection) -> list[str]:
    df = pd.read_sql_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'etf_%' ORDER BY name",
        conn,
    )
    return df["name"].tolist()


def detect_date_col(df: pd.DataFrame) -> str | None:
    for c in ("日期", "date", "Date"):
        if c in df.columns:
            return c
    return None


def read_table_dates(conn: sqlite3.Connection, table: str) -> pd.DatetimeIndex:
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    if df.empty:
        return pd.DatetimeIndex([])
    date_col = detect_date_col(df)
    if not date_col:
        return pd.DatetimeIndex([])
    d = pd.to_datetime(df[date_col], errors="coerce")
    d = d.dropna().dt.normalize()
    return pd.DatetimeIndex(sorted(d.unique()))


def read_daily_equity_dates(conn: sqlite3.Connection) -> pd.DatetimeIndex:
    try:
        df = pd.read_sql_query("SELECT date FROM daily_equity", conn)
    except Exception:
        return pd.DatetimeIndex([])
    if df.empty or "date" not in df.columns:
        return pd.DatetimeIndex([])
    d = pd.to_datetime(df["date"], errors="coerce")
    d = d.dropna().dt.normalize()
    return pd.DatetimeIndex(sorted(d.unique()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join("data", "etf_data.db"))
    ap.add_argument("--start", default="2025-11-27")
    ap.add_argument("--mode", choices=["union", "intersection"], default="union", help="Trading day inference mode")
    ap.add_argument("--limit_tables", type=int, default=0, help="Debug: limit number of ETF tables to scan")
    args = ap.parse_args()

    root = project_root()
    db_path = os.path.join(root, args.db) if not os.path.isabs(args.db) else args.db
    if not os.path.exists(db_path):
        raise SystemExit(f"DB not found: {db_path}")

    start = pd.to_datetime(args.start).normalize()

    conn = sqlite3.connect(db_path)
    try:
        tables = list_etf_tables(conn)
        if args.limit_tables and args.limit_tables > 0:
            tables = tables[: args.limit_tables]

        if not tables:
            raise SystemExit("No etf_* tables found.")

        # infer trading days from ETF tables
        inferred: pd.DatetimeIndex | None = None
        scanned = 0
        for t in tables:
            d = read_table_dates(conn, t)
            d = d[d >= start]
            if len(d) == 0:
                continue
            scanned += 1
            if inferred is None:
                inferred = d
            else:
                if args.mode == "union":
                    inferred = inferred.union(d)
                else:
                    inferred = inferred.intersection(d)

        inferred = inferred if inferred is not None else pd.DatetimeIndex([])
        inferred = pd.DatetimeIndex(sorted(inferred.unique()))

        eq_dates = read_daily_equity_dates(conn)
        eq_dates = eq_dates[eq_dates >= start]

    finally:
        conn.close()

    if len(inferred) == 0:
        raise SystemExit(f"No inferred trading days >= {start.date()} (mode={args.mode}).")

    inferred_set = set(inferred)
    eq_set = set(eq_dates)

    missing = sorted(list(inferred_set - eq_set))
    extra = sorted(list(eq_set - inferred_set))

    print("=== Missing daily_equity check (mode=B, inferred from ETF tables) ===")
    print(f"DB: {db_path}")
    print(f"Start: {start.date()} | mode={args.mode} | scanned_tables={scanned}/{len(tables)}")
    print(f"Inferred trading days: {len(inferred)} | range: {inferred.min().date()} -> {inferred.max().date()}")
    if len(eq_dates) == 0:
        print("daily_equity: 0 rows (no snapshots found)")
    else:
        print(f"daily_equity days: {len(eq_dates)} | range: {eq_dates.min().date()} -> {eq_dates.max().date()}")

    print(f"Missing equity days: {len(missing)}")
    if missing:
        print("First 50 missing days:")
        for d in missing[:50]:
            print(" -", d.date())

    if extra:
        print(f"Note: {len(extra)} equity days are not in inferred trading day set (could be due to limited symbol coverage).")

    out_dir = os.path.join(root, "out")
    ensure_dir(out_dir)
    out_fp = os.path.join(out_dir, f"missing_equity_days_{start.date()}_to_{inferred.max().date()}_{args.mode}.csv")

    out_df = pd.DataFrame({"date": [d.strftime("%Y-%m-%d") for d in missing]})
    out_df.to_csv(out_fp, index=False, encoding="utf-8-sig")
    print(f"Wrote: {out_fp}")


if __name__ == "__main__":
    main()

