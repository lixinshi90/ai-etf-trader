# -*- coding: utf-8 -*-
"""
近似版 Vegas 风险计算（无期权持仓）
- 用历史波动率 sigma 作为隐含波近似（rolling std * sqrt(252)）
- 用 ATM Black-Scholes Vega 的简化近似：Vega_proxy ≈ S * phi(0) * sqrt(T)
  其中 phi(0)=1/sqrt(2*pi)≈0.39894228，T为年化期限（T_days/365）
- 离散积分：delta_V(t) = Vega_proxy(t-1) * (sigma(t)-sigma(t-1))
- 输出序列：date, S, sigma, vega_proxy, delta_sigma, delta_V, cum_delta_V

依赖：读取 data/etf_data.db 中 etf_{code} 表。
"""
from __future__ import annotations

import math
import os
import sqlite3
from typing import List, Optional

import pandas as pd

PHI0 = 1.0 / math.sqrt(2.0 * math.pi)  # N(0,1)密度在0处


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _etf_db_path() -> str:
    return os.path.join(_project_root(), "data", "etf_data.db")


def _pick_col(df: pd.DataFrame, cols: List[str]) -> Optional[str]:
    for c in cols:
        if c in df.columns:
            return c
    return None


def _read_etf_df(code: str, limit: int = 800) -> pd.DataFrame:
    db = _etf_db_path()
    if not os.path.exists(db):
        return pd.DataFrame()
    conn = sqlite3.connect(db)
    try:
        try:
            df = pd.read_sql_query(f"SELECT * FROM etf_{code}", conn)
        except Exception:
            return pd.DataFrame()
    finally:
        conn.close()
    if df.empty:
        return df
    # 标准化日期并升序
    dcol = _pick_col(df, ["日期", "date", "Date"]) or "日期"
    df[dcol] = pd.to_datetime(df[dcol])
    df = df.sort_values(dcol)
    if len(df) > limit:
        df = df.tail(limit)
    df = df.reset_index(drop=True)
    return df


def compute_vega_proxy_series(code: str, vol_lookback: int = 20, T_days: int = 30, period: Optional[int] = None) -> pd.DataFrame:
    """返回包含 Vegas 近似序列的 DataFrame。
    列：date, S, sigma(年化, %), vega_proxy, delta_sigma, delta_V, cum_delta_V
    """
    df = _read_etf_df(code)
    if df.empty:
        return df
    dcol = _pick_col(df, ["日期", "date", "Date"]) or "日期"
    ccol = _pick_col(df, ["收盘", "收盘价", "close", "Close"]) or "收盘"

    out = pd.DataFrame({
        "date": pd.to_datetime(df[dcol]).dt.strftime("%Y-%m-%d"),
        "S": pd.to_numeric(df[ccol], errors="coerce").astype(float)
    })

    # 历史波动率（% 年化）
    ret = out["S"].pct_change()
    sigma_daily = ret.rolling(vol_lookback).std()
    sigma_annual = sigma_daily * math.sqrt(252.0) * 100.0
    out["sigma"] = sigma_annual

    # Vega 近似：S * phi(0) * sqrt(T)
    T_years = max(1, int(T_days)) / 365.0
    vega_proxy = out["S"] * PHI0 * math.sqrt(T_years)
    out["vega_proxy"] = vega_proxy

    # Δσ 与 ΔV（Δσ 为百分点变化，故与 vega_proxy 的量纲不同，仅用于相对观察）
    out["delta_sigma"] = out["sigma"].diff()
    out["delta_V"] = out["vega_proxy"].shift(1) * out["delta_sigma"].fillna(0.0)
    out["cum_delta_V"] = out["delta_V"].cumsum()

    if period is not None and period > 0 and len(out) > period:
        out = out.tail(period)
    return out.reset_index(drop=True)


def latest_summary(codes: List[str], vol_lookback: int = 20, T_days: int = 30) -> List[dict]:
    rows: List[dict] = []
    for code in codes:
        try:
            df = compute_vega_proxy_series(code, vol_lookback, T_days, period=None)
            if df.empty:
                continue
            r = df.iloc[-1]
            rows.append({
                "code": code,
                "date": str(r.get("date")),
                "sigma": float(r.get("sigma")) if pd.notna(r.get("sigma")) else None,
                "vega_proxy": float(r.get("vega_proxy")) if pd.notna(r.get("vega_proxy")) else None,
                "delta_sigma": float(r.get("delta_sigma")) if pd.notna(r.get("delta_sigma")) else None,
                "delta_V": float(r.get("delta_V")) if pd.notna(r.get("delta_V")) else None,
                "cum_delta_V": float(r.get("cum_delta_V")) if pd.notna(r.get("cum_delta_V")) else None,
            })
        except Exception:
            continue
    return rows

