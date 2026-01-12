# -*- coding: utf-8 -*-
"""
Non-intrusive bridge to prepare local ETF daily data for Qlib consumption.
- Read from data/etf_data.db (read-only)
- Export unified CSVs: data/qlib/raw/{symbol}.csv with columns:
    symbol,date,open,high,low,close,volume,adjfactor
- Generate calendar.txt and instruments.csv under data/qlib/raw/

This will NOT touch existing trade_history.db nor etf_data.db.

Usage:
  python -m src.qlib_adapter --etfs ENV   # read ETF_LIST from .env
  python -m src.qlib_adapter --etfs 510050,510300,159915   # explicit list

After export, you may convert CSVs to qlib binary provider (optional):
  # Requires pyqlib installed in a compatible environment
  # The following command path may vary by qlib version. If it fails,
  # please check qlib docs for the latest dump tool path.
  python -m qlib.scripts.dump_bin --csv_path data/qlib/raw \
      --qlib_dir data/qlib/cn_etf --max_workers 4 --symbol_field symbol

Alternatively, you can run src/qlib_run.py which will compute factors
directly from CSVs as a fallback even if qlib binary provider is not built.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from typing import List, Tuple

import pandas as pd
from dotenv import load_dotenv

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "qlib", "raw")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "etf_data.db")


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _detect_cols(df: pd.DataFrame) -> Tuple[str, str, str, str, str, str]:
    # returns: date_col, open_col, high_col, low_col, close_col, vol_col
    candidates = {
        "date": ["日期", "date", "Date"],
        "open": ["开盘", "open", "Open"],
        "high": ["最高", "high", "High"],
        "low": ["最低", "low", "Low"],
        "close": ["收盘", "收盘价", "close", "Close"],
        "volume": ["成交量", "volume", "Volume"],
    }
    out = []
    for key in ["date", "open", "high", "low", "close", "volume"]:
        found = None
        for col in candidates[key]:
            if col in df.columns:
                found = col
                break
        if not found:
            raise ValueError(f"missing column for {key}, available: {list(df.columns)}")
        out.append(found)
    return tuple(out)  # type: ignore


def export_symbol(conn: sqlite3.Connection, code: str, out_dir: str) -> int:
    # Try two table name patterns
    table = f"etf_{code}"
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    except Exception:
        # skip if not exists
        return 0
    if df.empty:
        return 0
    dcol, ocol, hcol, lcol, ccol, vcol = _detect_cols(df)
    df = df[[dcol, ocol, hcol, lcol, ccol, vcol]].copy()
    # normalize
    df.rename(columns={
        dcol: "date", ocol: "open", hcol: "high", lcol: "low",
        ccol: "close", vcol: "volume"
    }, inplace=True)
    # sort by date ascending
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values("date")
    df.insert(0, "symbol", code)
    df["adjfactor"] = 1.0  # ETFs commonly no split adjustment; adjust if needed

    _ensure_dir(out_dir)
    fpath = os.path.join(out_dir, f"{code}.csv")
    df.to_csv(fpath, index=False)
    return len(df)


def build_calendar_and_instruments(out_dir: str) -> None:
    # Aggregate all CSVs for calendar and instruments（容错：允许旧文件列名不是 date）
    import glob

    csv_files = sorted(glob.glob(os.path.join(out_dir, "*.csv")))
    dates = set()
    inst_rows = []
    for fp in csv_files:
        try:
            d = pd.read_csv(fp)
        except Exception:
            continue
        if d is None or d.empty:
            continue
        # 兼容不同列名：date / 日期 / Date
        date_col = None
        for c in ["date", "日期", "Date"]:
            if c in d.columns:
                date_col = c
                break
        if date_col is None:
            # 跳过不规范文件
            continue
        # 规范为 date 列
        if date_col != "date":
            d = d.rename(columns={date_col: "date"})
        # 转为日期并去除无效
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna(subset=["date"]).sort_values("date")
        if d.empty:
            continue

        s = os.path.splitext(os.path.basename(fp))[0]
        try:
            start = d["date"].min().strftime("%Y-%m-%d")
            end = d["date"].max().strftime("%Y-%m-%d")
        except Exception:
            continue
        inst_rows.append({"symbol": s, "start_date": start, "end_date": end})
        dates.update(d["date"].dt.strftime("%Y-%m-%d").tolist())

    cal = sorted(list(dates))
    # Write calendar.txt (one date per line)
    with open(os.path.join(out_dir, "calendar.txt"), "w", encoding="utf-8") as f:
        for d0 in cal:
            f.write(d0 + "\n")
    # Write instruments.csv
    if inst_rows:
        pd.DataFrame(inst_rows).to_csv(os.path.join(out_dir, "instruments.csv"), index=False)


def main(etfs: List[str]) -> None:
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"etf db not found: {DB_PATH}")
    out_dir = RAW_DIR
    _ensure_dir(out_dir)
    conn = sqlite3.connect(DB_PATH)
    total = 0
    try:
        for code in etfs:
            code = code.strip()
            if not code:
                continue
            cnt = export_symbol(conn, code, out_dir)
            print(f"[qlib_adapter] exported {code}: {cnt} rows")
            total += cnt
    finally:
        conn.close()
    build_calendar_and_instruments(out_dir)
    print(f"[qlib_adapter] done. total rows: {total}")
    print("Next (optional) convert to qlib binary provider:")
    print("  python -m qlib.scripts.dump_bin --csv_path data/qlib/raw")
    print("      --qlib_dir data/qlib/cn_etf --max_workers 4 --symbol_field symbol")


if __name__ == "__main__":
    load_dotenv(override=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--etfs", type=str, default="ENV", help="comma list or ENV to use ETF_LIST from .env")
    args = parser.parse_args()

    if args.etfs == "ENV":
        etf_env = os.getenv("ETF_LIST", "")
        etfs = [x.strip() for x in etf_env.split(",") if x.strip()]
    else:
        etfs = [x.strip() for x in args.etfs.split(",") if x.strip()]
    if not etfs:
        raise SystemExit("No ETFs provided. Set ETF_LIST in .env or pass --etfs 510050,510300,159915")
    main(etfs)
