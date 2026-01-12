# -*- coding: utf-8 -*-
"""
Audit trade prices against etf_data.db closes to verify they were computed from real ETF prices.

Rules:
- For each trade in data/trade_history.db, find close price for that symbol on trade date (date part only)
  from data/etf_data.db table etf_{code}.
- For BUY trades, expected exec price ~= close * (1 + SLIPPAGE_BPS/10000)
- For SELL trades, expected exec price ~= close * (1 - SLIPPAGE_BPS/10000)
- Allow relative tolerance (default 0.5% = 0.005) to account for rounding and intraday fill differences.
- Produce a summary report.

Usage:
  uv run python -m scripts.audit_prices
  uv run python -m scripts.audit_prices --tol 0.006 --since 2025-12-01

Outputs a human-readable report to stdout.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from typing import Tuple, Optional

import pandas as pd
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TRADE_DB = os.path.join(ROOT, "data", "trade_history.db")
ETF_DB = os.path.join(ROOT, "data", "etf_data.db")


def _read_trades(since: Optional[str]) -> pd.DataFrame:
    if not os.path.exists(TRADE_DB):
        raise SystemExit(f"trade db not found: {TRADE_DB}")
    conn = sqlite3.connect(TRADE_DB)
    try:
        df = pd.read_sql_query(
            "SELECT id, date, etf_code, action, price, quantity, capital_after FROM trades ORDER BY datetime(date)",
            conn,
        )
    finally:
        conn.close()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    if since:
        try:
            cutoff = pd.to_datetime(since)
            df = df[df["date"] >= cutoff]
        except Exception:
            pass
    return df


def _read_close(code: str, day: pd.Timestamp) -> Optional[float]:
    if not os.path.exists(ETF_DB):
        return None
    conn = sqlite3.connect(ETF_DB)
    try:
        try:
            d = pd.read_sql_query(f"SELECT * FROM etf_{code}", conn)
        except Exception:
            return None
    finally:
        conn.close()
    if d is None or d.empty:
        return None
    # detect date, close columns (CN/EN compatibility)
    date_col = next((c for c in ("日期", "date", "Date") if c in d.columns), None)
    close_col = next((c for c in ("收盘", "收盘价", "close", "Close") if c in d.columns), None)
    if not date_col or not close_col:
        return None
    d[date_col] = pd.to_datetime(d[date_col], errors="coerce")
    d = d.dropna(subset=[date_col])
    d = d.sort_values(date_col)
    target = pd.to_datetime(day.date())
    # prefer exact date, else fallback to last available before date (in case of missing)
    exact = d[d[date_col] == target]
    if not exact.empty:
        v = exact.iloc[-1][close_col]
    else:
        prev = d[d[date_col] <= target]
        if prev.empty:
            return None
        v = prev.iloc[-1][close_col]
    try:
        return float(v)
    except Exception:
        return None


def main(tol: float, since: Optional[str]) -> None:
    load_dotenv(override=True)
    try:
        slip_bps = float(os.getenv("SLIPPAGE_BPS", "2"))
    except Exception:
        slip_bps = 2.0
    slip = slip_bps / 10000.0

    trades = _read_trades(since)
    if trades.empty:
        print("No trades to audit.")
        return

    total = 0
    matched = 0
    missing_px = 0
    rows = []

    for _, r in trades.iterrows():
        total += 1
        code = str(r.get("etf_code") or "").strip()
        action = str(r.get("action") or "").lower()
        price = float(r.get("price") or 0.0)
        day = pd.to_datetime(r.get("date"))
        if not code or price <= 0 or pd.isna(day):
            rows.append({"id": int(r.get("id", 0)), "code": code, "date": str(day), "action": action, "price": price, "close": None, "expected": None, "rel_err": None, "ok": False, "reason": "invalid trade"})
            continue
        close = _read_close(code, day)
        if close is None or close <= 0:
            missing_px += 1
            rows.append({"id": int(r.get("id", 0)), "code": code, "date": day.strftime('%Y-%m-%d'), "action": action, "price": price, "close": None, "expected": None, "rel_err": None, "ok": False, "reason": "no close"})
            continue
        expected = close * (1.0 + slip if action == "buy" else (1.0 - slip) if action == "sell" else 1.0)
        rel_err = abs(price - expected) / expected if expected > 0 else None
        ok = (rel_err is not None) and (rel_err <= tol or action == "hold")
        if ok:
            matched += 1
        rows.append({
            "id": int(r.get("id", 0)),
            "code": code,
            "date": day.strftime('%Y-%m-%d'),
            "action": action,
            "price": round(price, 6),
            "close": round(close, 6),
            "expected": round(expected, 6),
            "rel_err": round(rel_err, 6) if rel_err is not None else None,
            "ok": ok,
            "reason": None if ok else "mismatch"
        })

    # Summary
    print("=== Audit Summary ===")
    print(f"Trades audited: {total}")
    print(f"Matched (<= {tol*100:.2f}% tol): {matched}")
    print(f"Missing close price: {missing_px}")
    print(f"Mismatches: {total - matched - missing_px}")

    # Show first 20 mismatches
    mism = [x for x in rows if not x["ok"]]
    if mism:
        print("\n--- Mismatches (first 20) ---")
        for x in mism[:20]:
            print(x)
    else:
        print("\nNo mismatches under tolerance.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=0.005, help="relative tolerance (default 0.005 = 0.5%)")
    ap.add_argument("--since", type=str, default=None, help="only audit trades on/after this date (YYYY-MM-DD)")
    args = ap.parse_args()
    main(args.tol, args.since)

