# -*- coding: utf-8 -*-
"""Explain/verify equity composition on a given day.

目标：解决“净值构成是否真实”的疑虑。

做法：
1) 从 out/resimulated_trades_fully_compliant.csv 重建截至指定日期（含当日所有交易之后）的持仓数量与现金。
2) 从 data/etf_data.db 读取每个持仓标的在该日期的收盘价（若该日无数据，可选择向前回退最近交易日）。
3) 逐标的计算估值并汇总，输出对账结果。

Usage:
  uv run python scripts/explain_equity_day.py --date 2025-12-11

Outputs:
  - out/equity_explain_<date>.csv
  - prints summary and any price fallbacks.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from dataclasses import dataclass

import pandas as pd


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def read_prices_for_date(conn: sqlite3.Connection, etf_code: str, target_date: pd.Timestamp) -> tuple[float | None, str]:
    """Return (close_price, used_date_str).

    If exact date is not found, fallback to the latest available date <= target_date.
    """
    table = f"etf_{etf_code}"

    # Read minimal columns; different schemas exist.
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    except Exception:
        return None, ""

    if df.empty:
        return None, ""

    date_col = next((c for c in ("日期", "date", "Date") if c in df.columns), None)
    close_col = next((c for c in ("收盘", "收盘价", "close", "Close") if c in df.columns), None)
    if not date_col or not close_col:
        return None, ""

    d = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    c = pd.to_numeric(df[close_col], errors="coerce")
    tmp = pd.DataFrame({"d": d, "c": c}).dropna()
    tmp = tmp[tmp["c"] > 0]
    if tmp.empty:
        return None, ""

    # exact match
    exact = tmp[tmp["d"] == target_date]
    if not exact.empty:
        return float(exact.iloc[-1]["c"]), target_date.strftime("%Y-%m-%d")

    # fallback to <= date
    prior = tmp[tmp["d"] <= target_date]
    if prior.empty:
        return None, ""
    prior = prior.sort_values("d")
    used = prior.iloc[-1]
    return float(used["c"]), pd.Timestamp(used["d"]).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Target date, e.g. 2025-12-11")
    ap.add_argument("--trades", default=os.path.join("out", "resimulated_trades_fully_compliant.csv"))
    ap.add_argument("--market_db", default=os.path.join("data", "etf_data.db"))
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    root = project_root()
    target_date = pd.to_datetime(args.date).normalize()

    trades_path = os.path.join(root, args.trades) if not os.path.isabs(args.trades) else args.trades
    market_db = os.path.join(root, args.market_db) if not os.path.isabs(args.market_db) else args.market_db

    if not os.path.exists(trades_path):
        raise SystemExit(f"Trades CSV not found: {trades_path}")
    if not os.path.exists(market_db):
        raise SystemExit(f"Market DB not found: {market_db}")

    df = pd.read_csv(trades_path)
    if df.empty:
        raise SystemExit("Trades CSV is empty")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")

    # 截止到 target_date 当日 23:59:59 的所有交易
    end_ts = target_date + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    df_day = df[df["date"] <= end_ts].copy()

    # 重建现金与持仓（使用 value 字段；sell 用 +，buy 用 -）
    cash = 100000.0
    positions: dict[str, float] = {}

    for _, r in df_day.iterrows():
        code = str(r.get("etf_code"))
        action = str(r.get("action")).lower()
        qty = float(r.get("quantity") or 0.0)
        value = float(r.get("value") or 0.0)

        if action == "buy":
            cash -= value
            positions[code] = positions.get(code, 0.0) + qty
        elif action == "sell":
            cash += value
            positions[code] = positions.get(code, 0.0) - qty
        else:
            continue

    # 清理接近 0 的残余
    positions = {k: v for k, v in positions.items() if abs(v) > 1e-8}

    # 估值
    conn = sqlite3.connect(market_db)
    rows = []
    fallbacks = []
    missing_px = []

    try:
        for code, qty in sorted(positions.items()):
            px, used_date = read_prices_for_date(conn, code, target_date)
            if px is None:
                missing_px.append(code)
                px = 0.0
                used_date = ""
            if used_date and used_date != target_date.strftime("%Y-%m-%d"):
                fallbacks.append((code, used_date))
            rows.append({
                "date": target_date.strftime("%Y-%m-%d"),
                "etf_code": code,
                "qty": qty,
                "close": px,
                "price_date_used": used_date,
                "value": qty * px,
            })
    finally:
        conn.close()

    out_df = pd.DataFrame(rows)
    holdings_value = float(out_df["value"].sum()) if not out_df.empty else 0.0
    total_assets = cash + holdings_value

    print("=== Equity explain ===")
    print("Target date:", target_date.date())
    print(f"Cash (reconstructed): {cash:.6f}")
    print(f"Holdings value (mark-to-close): {holdings_value:.6f}")
    print(f"Total assets: {total_assets:.6f}")
    print(f"Positions count: {len(out_df)}")

    if fallbacks:
        print("\n[price-fallback] used previous available close for:")
        for code, used_date in fallbacks:
            print(f" - {code}: used {used_date}")

    if missing_px:
        print("\n[missing-price] no close found (value treated as 0):")
        for code in missing_px:
            print(" -", code)

    out_dir = os.path.join(root, args.out)
    ensure_dir(out_dir)
    out_fp = os.path.join(out_dir, f"equity_explain_{target_date.strftime('%Y-%m-%d')}.csv")
    out_df.to_csv(out_fp, index=False, encoding="utf-8-sig")
    print("Wrote:", out_fp)


if __name__ == "__main__":
    main()

