# -*- coding: utf-8 -*-
"""
Lightweight factor computation directly from CSVs exported by src.qlib_adapter
(does NOT require qlib provider). This keeps your existing DBs untouched.

Input:  data/qlib/raw/{symbol}.csv  with columns:
        symbol,date,open,high,low,close,volume,adjfactor
Output: data/qlib_factors/{symbol}.csv with columns:
        date,symbol,ret_1d_pct,vol_20d_pct,rsi_14

Usage (project root):
  conda activate qlib-env  # or any py>=3.8 environment with pandas/numpy
  python -m src.qlib_run

You can control which symbols to process via .env ETF_LIST or by --etfs ...
  python -m src.qlib_run --etfs 510050,510300,159915
"""
from __future__ import annotations

import argparse
import os
from typing import List

import numpy as np
import pandas as pd
from dotenv import load_dotenv

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "qlib", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "qlib_factors")


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def compute_factors_one(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if df.empty:
        return df
    # normalize
    for col in ["date", "symbol", "close"]:
        if col not in df.columns:
            raise ValueError(f"{csv_path}: missing column {col}")
    df["date"] = pd.to_datetime(df["date"])  # type: ignore
    df = df.sort_values("date")

    # 1) 1-day return (%)
    close = df["close"].astype(float)
    ret_1d = close.pct_change() * 100.0

    # 2) 20-day volatility annualized (%) based on 1d returns
    vol_20d = ret_1d.rolling(20).std() * np.sqrt(252.0)

    # 3) RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    roll_up = gain.rolling(14).mean()
    roll_down = loss.rolling(14).mean()
    rs = roll_up / (roll_down.replace(0.0, np.nan))
    rsi_14 = 100.0 - (100.0 / (1.0 + rs))

    out = pd.DataFrame({
        "date": df["date"].dt.strftime("%Y-%m-%d"),
        "symbol": df["symbol"],
        "ret_1d_pct": ret_1d.round(4),
        "vol_20d_pct": vol_20d.round(4),
        "rsi_14": rsi_14.round(2),
    })
    return out


def run(etfs: List[str]) -> None:
    _ensure_dir(OUT_DIR)
    total = 0
    for code in etfs:
        code = code.strip()
        if not code:
            continue
        csv_path = os.path.join(RAW_DIR, f"{code}.csv")
        if not os.path.exists(csv_path):
            print(f"[qlib_run] skip {code}, not found: {csv_path}")
            continue
        out_df = compute_factors_one(csv_path)
        if out_df.empty:
            print(f"[qlib_run] {code}: no rows")
            continue
        out_fp = os.path.join(OUT_DIR, f"{code}.csv")
        out_df.to_csv(out_fp, index=False)
        print(f"[qlib_run] {code}: wrote {len(out_df)} rows -> {out_fp}")
        total += len(out_df)
    print(f"[qlib_run] done. total rows: {total}")


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
    run(etfs)

