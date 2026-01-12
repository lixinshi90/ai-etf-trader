# -*- coding: utf-8 -*-
"""Backfill missing daily_equity entries using trades replay + market close prices.

口径：
- 现金与持仓：从 data/trade_history.db 的 trades 流水“完整回放”（含成本，从 reasoning 解析 "成本: x.xx"）
- 估值：用 data/etf_data.db 在该交易日的收盘价（若该日无收盘价则向前回退最近 <= 当日 的收盘价）

默认策略：
- 只补缺失日（INSERT），不覆盖已有 daily_equity

Usage:
  uv run python scripts/backfill_daily_equity.py --dates 2025-12-04,2025-12-10

Outputs:
  - out/backfill_daily_equity_report.csv
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from typing import Dict, Tuple

import pandas as pd


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def parse_cost(reasoning: str) -> float:
    if not reasoning:
        return 0.0
    m = re.search(r"成本:\s*([0-9]+(?:\.[0-9]+)?)", reasoning)
    return float(m.group(1)) if m else 0.0


def read_close_asof(etf_conn: sqlite3.Connection, code: str, date_str: str) -> Tuple[float | None, str]:
    """Return (close, used_date). If not found exact, fallback to latest <= date_str."""
    table = f"etf_{code}"

    # Chinese schema
    try:
        row = etf_conn.execute(
            f"SELECT 日期, 收盘 FROM {table} WHERE 日期 <= ? ORDER BY 日期 DESC LIMIT 1",
            (date_str,),
        ).fetchone()
        if row and row[1] is not None:
            return float(row[1]), str(row[0])
    except Exception:
        pass

    # English schema
    try:
        row = etf_conn.execute(
            f"SELECT date, close FROM {table} WHERE date <= ? ORDER BY date DESC LIMIT 1",
            (date_str,),
        ).fetchone()
        if row and row[1] is not None:
            return float(row[1]), str(row[0])
    except Exception:
        pass

    return None, ""


def infer_initial_cash_from_first_trade(trades_df: pd.DataFrame, default_ic: float) -> float:
    if trades_df.empty:
        return default_ic
    first = trades_df.iloc[0]
    act = str(first.get("action") or "").lower()
    gross = float(first.get("value") or 0.0)
    cap_after = float(first.get("capital_after") or 0.0)
    cost = parse_cost(str(first.get("reasoning") or ""))

    if act == "buy":
        # cap_after = cash_before - (gross + cost)
        return cap_after + gross + cost
    if act == "sell":
        # cap_after = cash_before + (gross - cost)
        return cap_after - gross + cost
    return default_ic


def replay_state_asof(trades_df: pd.DataFrame, date_str: str, default_ic: float) -> Tuple[float, Dict[str, float]]:
    """Replay cash + position quantities up to date_str 23:59:59."""
    cutoff = pd.to_datetime(date_str) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    df = trades_df[trades_df["dt"] <= cutoff].copy()

    init_cash = infer_initial_cash_from_first_trade(df, default_ic)
    cash = float(init_cash)
    pos: Dict[str, float] = {}

    for _, r in df.iterrows():
        code = str(r.get("etf_code") or "").strip()
        act = str(r.get("action") or "").lower()
        qty = float(r.get("quantity") or 0.0)
        gross = float(r.get("value") or 0.0)
        cost = parse_cost(str(r.get("reasoning") or ""))

        if not code or code == "ADJ":
            continue

        if act == "buy":
            cash -= (gross + cost)
            pos[code] = pos.get(code, 0.0) + qty
        elif act == "sell":
            cash += (gross - cost)
            pos[code] = pos.get(code, 0.0) - qty

    # keep positive holdings only
    pos = {c: q for c, q in pos.items() if q > 1e-9}
    return cash, pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", required=True, help="Comma-separated dates to backfill, e.g. 2025-12-04,2025-12-10")
    ap.add_argument("--trade_db", default=os.path.join("data", "trade_history.db"))
    ap.add_argument("--etf_db", default=os.path.join("data", "etf_data.db"))
    ap.add_argument("--out", default=os.path.join("out", "backfill_daily_equity_report.csv"))
    args = ap.parse_args()

    root = project_root()
    trade_db = os.path.join(root, args.trade_db) if not os.path.isabs(args.trade_db) else args.trade_db
    etf_db = os.path.join(root, args.etf_db) if not os.path.isabs(args.etf_db) else args.etf_db
    out_fp = os.path.join(root, args.out) if not os.path.isabs(args.out) else args.out

    dates = [d.strip() for d in str(args.dates).split(",") if d.strip()]
    if not dates:
        raise SystemExit("No dates provided")

    if not os.path.exists(trade_db):
        raise SystemExit(f"trade_db not found: {trade_db}")
    if not os.path.exists(etf_db):
        raise SystemExit(f"etf_db not found: {etf_db}")

    # Load trades
    tconn = sqlite3.connect(trade_db)
    try:
        tdf = pd.read_sql_query(
            "SELECT date, etf_code, action, quantity, value, capital_after, reasoning FROM trades ORDER BY datetime(date)",
            tconn,
        )
    finally:
        tconn.close()

    tdf["dt"] = pd.to_datetime(tdf["date"], errors="coerce")
    tdf = tdf.dropna(subset=["dt"]).copy()

    default_ic = float(os.getenv("INITIAL_CAPITAL", "100000"))

    # Ensure output dir
    ensure_dir(os.path.dirname(out_fp))

    # Open DBs
    conn_trade = sqlite3.connect(trade_db)
    conn_etf = sqlite3.connect(etf_db)

    report_rows = []

    try:
        conn_trade.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")

        for d in dates:
            # skip if exists
            exist = conn_trade.execute("SELECT 1 FROM daily_equity WHERE date = ? LIMIT 1", (d,)).fetchone()
            if exist:
                report_rows.append({"date": d, "status": "skipped_exists", "cash": None, "holdings_value": None, "equity": None, "missing_px": "", "fallback_px": ""})
                continue

            cash, pos = replay_state_asof(tdf, d, default_ic)

            holdings_value = 0.0
            missing = []
            fallbacks = []
            for code, qty in pos.items():
                px, used_date = read_close_asof(conn_etf, code, d)
                if px is None or px <= 0:
                    missing.append(code)
                    continue
                if used_date and used_date != d:
                    fallbacks.append(f"{code}:{used_date}")
                holdings_value += float(qty) * float(px)

            equity = float(cash) + float(holdings_value)

            if missing:
                # do not write if missing prices (safety)
                report_rows.append({
                    "date": d,
                    "status": "failed_missing_px",
                    "cash": round(cash, 6),
                    "holdings_value": round(holdings_value, 6),
                    "equity": round(equity, 6),
                    "missing_px": ";".join(missing),
                    "fallback_px": ";".join(fallbacks),
                })
                continue

            conn_trade.execute("INSERT INTO daily_equity(date, equity) VALUES(?,?)", (d, float(equity)))
            conn_trade.commit()

            report_rows.append({
                "date": d,
                "status": "inserted",
                "cash": round(cash, 6),
                "holdings_value": round(holdings_value, 6),
                "equity": round(equity, 6),
                "missing_px": "",
                "fallback_px": ";".join(fallbacks),
            })

    finally:
        conn_etf.close()
        conn_trade.close()

    rep = pd.DataFrame(report_rows)
    rep.to_csv(out_fp, index=False, encoding="utf-8-sig")
    print(f"Wrote report: {out_fp}")
    print(rep.to_string(index=False))


if __name__ == "__main__":
    main()

