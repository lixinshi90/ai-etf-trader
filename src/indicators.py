# -*- coding: utf-8 -*-
"""
技术指标计算模块：KDJ, MACD
- 所有函数接收一个 pandas DataFrame，并返回一个带有新增指标列的 DataFrame。
- 兼容不同的列名（如 '收盘' vs 'close'）。
"""
from __future__ import annotations
import pandas as pd

def _safe_col(df: pd.DataFrame, name_candidates: list[str]) -> str | None:
    for c in name_candidates:
        if c in df.columns:
            return c
    return None

def add_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """计算 KDJ 指标并添加到 DataFrame。"""
    df_out = df.copy()
    close_col = _safe_col(df_out, ["收盘", "收盘价", "close", "Close"])
    high_col = _safe_col(df_out, ["最高", "最高价", "high", "High"])
    low_col = _safe_col(df_out, ["最低", "最低价", "low", "Low"])

    if not all([close_col, high_col, low_col]):
        # 缺少必要列，返回原 DataFrame
        return df

    # 计算 RSV
    low_n = df_out[low_col].rolling(n, min_periods=1).min()
    high_n = df_out[high_col].rolling(n, min_periods=1).max()
    rsv = (df_out[close_col] - low_n) / (high_n - low_n) * 100
    rsv = rsv.fillna(0) # 处理分母为0的情况

    # 计算 K, D, J
    df_out['k'] = rsv.ewm(com=m1 - 1, adjust=False).mean()
    df_out['d'] = df_out['k'].ewm(com=m2 - 1, adjust=False).mean()
    df_out['j'] = 3 * df_out['k'] - 2 * df_out['d']
    return df_out

def add_macd(df: pd.DataFrame, short: int = 12, long: int = 26, mid: int = 9) -> pd.DataFrame:
    """计算 MACD 指标并添加到 DataFrame。"""
    df_out = df.copy()
    close_col = _safe_col(df_out, ["收盘", "收盘价", "close", "Close"])

    if not close_col:
        return df

    # 计算 DIF, DEA, MACD
    ema_short = df_out[close_col].ewm(span=short, adjust=False).mean()
    ema_long = df_out[close_col].ewm(span=long, adjust=False).mean()
    df_out['dif'] = ema_short - ema_long
    df_out['dea'] = df_out['dif'].ewm(span=mid, adjust=False).mean()
    df_out['macd'] = (df_out['dif'] - df_out['dea']) * 2
    return df_out

