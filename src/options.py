# -*- coding: utf-8 -*-
"""
Black–Scholes 工具箱 + ETF期权链抓取与IV/Greeks计算（akshare 1.17.88 适配）
- bs_price: 欧式看涨/看跌定价
- greeks: Delta/Gamma/Vega/Theta/Rho
- implied_vol: 由市场期权价格反推隐含波动率（牛顿+夹逼兜底）
- try_fetch_option_chain_from_ak: 抓取上交所ETF期权链并标准化字段；失败时尝试读取本地 data/options/{code}.csv 作为离线兜底
- get_option_chain_with_iv_greeks: 在链条上补充 IV 与 Greeks
- get_atm_iv_summary: 平值合约 IV 概览
"""
from __future__ import annotations

import math
from typing import Dict, Optional
from datetime import datetime, timedelta

import os
import pandas as pd

# ---- 尝试导入 akshare（可选） ----
try:
    import akshare as ak  # type: ignore
except Exception:  # pragma: no cover
    ak = None

SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1_d2(S: float, K: float, T: float, r: float, q: float, sigma: float) -> tuple[float, float]:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0, 0.0
    mu = math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T
    den = sigma * math.sqrt(T)
    d1 = mu / den
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def bs_price(S: float, K: float, T: float, r: float, q: float, sigma: float, opt_type: str = "call") -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    df_r = math.exp(-r * T)
    df_q = math.exp(-q * T)
    if opt_type.lower() == "call":
        return S * df_q * _norm_cdf(d1) - K * df_r * _norm_cdf(d2)
    else:
        return K * df_r * _norm_cdf(-d2) - S * df_q * _norm_cdf(-d1)


def greeks(S: float, K: float, T: float, r: float, q: float, sigma: float, opt_type: str = "call") -> Dict[str, float]:
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    df_r = math.exp(-r * T)
    df_q = math.exp(-q * T)
    pdf_d1 = _norm_pdf(d1)

    delta_call = df_q * _norm_cdf(d1)
    delta_put = delta_call - df_q
    gamma = df_q * pdf_d1 / (S * sigma * math.sqrt(T)) if S > 0 and sigma > 0 and T > 0 else 0.0
    vega = S * df_q * pdf_d1 * math.sqrt(T)

    if opt_type.lower() == "call":
        theta = - (S * df_q * pdf_d1 * sigma) / (2.0 * math.sqrt(T)) - r * K * df_r * _norm_cdf(d2) + q * S * df_q * _norm_cdf(d1)
        rho = K * T * df_r * _norm_cdf(d2)
        delta = delta_call
    else:
        theta = - (S * df_q * pdf_d1 * sigma) / (2.0 * math.sqrt(T)) + r * K * df_r * _norm_cdf(-d2) - q * S * df_q * _norm_cdf(-d1)
        rho = -K * T * df_r * _norm_cdf(-d2)
        delta = delta_put

    return {"delta": float(delta), "gamma": float(gamma), "vega": float(vega), "theta": float(theta), "rho": float(rho)}


def implied_vol(S: float, K: float, T: float, r: float, q: float, price: float, opt_type: str = "call",
                 init: float = 0.3, tol: float = 1e-6, max_iter: int = 100, lo: float = 1e-4, hi: float = 5.0) -> float:
    if S <= 0 or K <= 0 or T <= 0 or price <= 0:
        return float("nan")
    sigma = max(lo, min(hi, init))
    for _ in range(max_iter // 2):
        p = bs_price(S, K, T, r, q, sigma, opt_type)
        v = greeks(S, K, T, r, q, sigma, opt_type)["vega"]
        diff = p - price
        if abs(diff) < tol:
            return float(sigma)
        if v <= 1e-12:
            break
        sigma -= diff / v
        if sigma <= lo or sigma >= hi:
            break
    l, h = lo, hi
    for _ in range(max_iter):
        mid = 0.5 * (l + h)
        p_mid = bs_price(S, K, T, r, q, mid, opt_type)
        if abs(p_mid - price) < tol:
            return float(mid)
        if p_mid > price:
            h = mid
        else:
            l = mid
    return float("nan")


# ================== ETF 期权链（akshare 1.17.88） ==================

def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def try_fetch_option_chain_from_ak(etf_code: str, max_expiry_days: int = 30) -> pd.DataFrame:
    """抓取上交所ETF期权链（优先 fund_etf_option_sse），失败时尝试旧接口与离线CSV兜底。
    返回列：option_type, strike, bid, ask, mid, expiry, contract_code, volume, open_interest
    """
    # 1) 优先使用新版接口 fund_etf_option_sse
    df_raw = None
    if ak is not None and hasattr(ak, 'fund_etf_option_sse'):
        try:
            df_raw = ak.fund_etf_option_sse(symbol=etf_code)
        except Exception:
            df_raw = None

    # 2) 回退旧接口 + 多symbol变体
    if (df_raw is None or df_raw.empty) and ak is not None:
        for sym in [etf_code, f"{etf_code}.SH", f"{etf_code}.SSE"]:
            try:
                if hasattr(ak, 'fund_etf_option_chain_em'):
                    df_raw = ak.fund_etf_option_chain_em(symbol=sym, exchange="SSE")
                    if df_raw is not None and not df_raw.empty:
                        break
            except Exception:
                continue

    # 3) 离线CSV兜底（data/options/{code}.csv）
    if df_raw is None or df_raw.empty:
        csv_path = os.path.join(_project_root(), 'data', 'options', f'{etf_code}.csv')
        if os.path.exists(csv_path):
            try:
                df_raw = pd.read_csv(csv_path)
            except Exception:
                df_raw = None

    if df_raw is None or df_raw.empty:
        return pd.DataFrame()

    # 标准化映射
    mapped = pd.DataFrame()
    if "合约类型" in df_raw.columns:
        mapped["option_type"] = df_raw["合约类型"].map({"认购": "call", "认沽": "put"}).astype(str)
    elif "option_type" in df_raw.columns:
        mapped["option_type"] = df_raw["option_type"].map({"认购": "call", "认沽": "put", "call": "call", "put": "put"}).astype(str)
    else:
        return pd.DataFrame()

    mapped["strike"] = pd.to_numeric(df_raw.get("行权价", df_raw.get("strike")), errors="coerce")
    mapped["bid"] = pd.to_numeric(df_raw.get("买一价", df_raw.get("bid")), errors="coerce")
    mapped["ask"] = pd.to_numeric(df_raw.get("卖一价", df_raw.get("ask")), errors="coerce")
    mapped["mid"] = (mapped["bid"] + mapped["ask"]) / 2.0
    mapped["expiry"] = pd.to_datetime(df_raw.get("到期日", df_raw.get("expiry")), errors="coerce")
    mapped["contract_code"] = df_raw.get("合约代码", df_raw.get("contract_code"))
    mapped["volume"] = pd.to_numeric(df_raw.get("成交量", df_raw.get("volume")), errors="coerce").fillna(0).astype(int)
    mapped["open_interest"] = pd.to_numeric(df_raw.get("持仓量", df_raw.get("open_interest")), errors="coerce").fillna(0).astype(int)

    # 过滤
    mapped = mapped[(mapped["bid"] > 0) & (mapped["ask"] > 0) & mapped["expiry"].notna()]
    if mapped.empty:
        return mapped

    # 近月
    today = datetime.now()
    mapped = mapped[(mapped["expiry"] - today).dt.days <= int(max_expiry_days)]
    if mapped.empty:
        return mapped

    mapped = mapped.sort_values(["expiry", "strike", "option_type"]).reset_index(drop=True)
    return mapped


def fetch_etf_latest_price(etf_code: str) -> float:
    if ak is None:
        return 0.0
    try:
        df = ak.fund_etf_hist_em(
            symbol=etf_code,
            period="daily",
            start_date=(datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust="qfq",
        )
        if df is not None and not df.empty:
            for c in ("收盘", "收盘价", "close", "Close"):
                if c in df.columns:
                    try:
                        return float(df[c].iloc[-1])
                    except Exception:
                        continue
        return 0.0
    except Exception:
        return 0.0


def _risk_free_rate_env(default: float = 0.02) -> float:
    try:
        return float(os.getenv("RISK_FREE_RATE", str(default)))
    except Exception:
        return default


def get_option_chain_with_iv_greeks(etf_code: str, max_expiry_days: int = 30) -> pd.DataFrame:
    chain = try_fetch_option_chain_from_ak(etf_code, max_expiry_days=max_expiry_days)
    if chain is None or chain.empty:
        return pd.DataFrame()
    S = fetch_etf_latest_price(etf_code)
    if S <= 0:
        return pd.DataFrame()
    r = _risk_free_rate_env(0.02)
    q = 0.0

    out = chain.copy()
    iv_list, delta_list, gamma_list, vega_list, theta_list = [], [], [], [], []
    for _, row in out.iterrows():
        try:
            K = float(row["strike"])
            mid = float(row["mid"]) if pd.notna(row["mid"]) else 0.0
            if mid <= 0:
                iv_list.append(float("nan")); delta_list.append(float("nan")); gamma_list.append(float("nan")); vega_list.append(float("nan")); theta_list.append(float("nan"))
                continue
            T_days = max(0, int((row["expiry"] - datetime.now()).days))
            if T_days <= 0:
                iv_list.append(float("nan")); delta_list.append(float("nan")); gamma_list.append(float("nan")); vega_list.append(float("nan")); theta_list.append(float("nan"))
                continue
            T = T_days / 365.0
            opt_type = str(row["option_type"]).lower()
            iv = implied_vol(S, K, T, r, q, mid, opt_type=opt_type)
            if not (iv == iv):
                iv = float("nan")
            g = greeks(S, K, T, r, q, iv if iv == iv else 0.3, opt_type=opt_type)
            iv_list.append(iv)
            delta_list.append(g.get("delta"))
            gamma_list.append(g.get("gamma"))
            vega_list.append(g.get("vega"))
            theta_list.append(g.get("theta"))
        except Exception:
            iv_list.append(float("nan")); delta_list.append(float("nan")); gamma_list.append(float("nan")); vega_list.append(float("nan")); theta_list.append(float("nan"))
            continue

    out["iv"] = iv_list
    out["delta"] = delta_list
    out["gamma"] = gamma_list
    out["vega"] = vega_list
    out["theta"] = theta_list
    return out


def get_atm_iv_summary(etf_code: str, max_expiry_days: int = 30) -> Dict[str, Optional[float]]:
    chain = get_option_chain_with_iv_greeks(etf_code, max_expiry_days=max_expiry_days)
    if chain is None or chain.empty:
        return {"etf_code": etf_code, "atm_iv": None, "iv_7d_mean": None, "expiry_date": None, "strike": None, "option_type": None}
    S = fetch_etf_latest_price(etf_code)
    if S <= 0:
        return {"etf_code": etf_code, "atm_iv": None, "iv_7d_mean": None, "expiry_date": None, "strike": None, "option_type": None}
    df2 = chain.copy()
    df2["_dist"] = (pd.to_numeric(df2["strike"], errors="coerce") - S).abs()
    df2 = df2.sort_values(["expiry", "_dist"]).head(1)
    if df2.empty:
        return {"etf_code": etf_code, "atm_iv": None, "iv_7d_mean": None, "expiry_date": None, "strike": None, "option_type": None}
    r0 = df2.iloc[0]
    return {
        "etf_code": etf_code,
        "atm_iv": float(r0.get("iv")) if pd.notna(r0.get("iv")) else None,
        "iv_7d_mean": None,
        "expiry_date": str(pd.to_datetime(r0.get("expiry")).date()) if pd.notna(r0.get("expiry")) else None,
        "strike": float(r0.get("strike")) if pd.notna(r0.get("strike")) else None,
        "option_type": str(r0.get("option_type")) if pd.notna(r0.get("option_type")) else None,
    }
