# -*- coding: utf-8 -*-
"""
提示词与消息构建模块
"""
from __future__ import annotations

import os
import pandas as pd

SYSTEM_PROMPT = """
你是专业的ETF投资顾问，拥有15年金融市场经验，擅长趋势跟踪与均值回归策略。
分析原则：
1. 趋势为王：优先考虑价格趋势，上涨趋势中寻找买入机会，下跌趋势中寻找卖出机会
2. 量价分析：成交量放大配合价格突破为强信号
3. 均值回归：价格远离均线时，考虑反向操作
4. 风险控制：严格设置止损止盈，保护资金
5. 理性决策：基于数据和统计，不受情绪影响

决策必须输出以下JSON格式：
{
  "decision": "buy" | "sell" | "hold",
  "confidence": 0.0-1.0,
  "reasoning": "分析理由（中文，50-100字）",
  "target_price": 数值（目标价，合理范围内），
  "stop_loss": 数值（止损价，合理范围内），
  "take_profit": 数值（止盈价，合理范围内）
}
"""

# Few-shot 示例（可通过环境变量 FEW_SHOT_ENABLED 控制是否注入）
FEW_SHOTS = [
    {
        "role": "user",
        "content": "示例：价格高于MA20且量能放大，突破20日高点；请用JSON给出决策。"
    },
    {
        "role": "assistant",
        "content": '{"decision":"buy","confidence":0.72,"reasoning":"趋势向上且放量突破前高，风险可控","target_price":null,"stop_loss":null,"take_profit":null}'
    },
    {
        "role": "user",
        "content": "示例：价格低于MA20且量能萎缩，未见关键位突破；请用JSON给出决策。"
    },
    {
        "role": "assistant",
        "content": '{"decision":"hold","confidence":0.60,"reasoning":"趋势偏弱且量价配合不足，缺少入场信号","target_price":null,"stop_loss":null,"take_profit":null}'
    }
]


def _safe_col(df: pd.DataFrame, name_candidates: list[str]) -> str | None:
    for c in name_candidates:
        if c in df.columns:
            return c
    return None

# --- 新增：指标计算 ---

def _atr(df: pd.DataFrame, h: str, l: str, c: str, n: int = 14) -> float:
    d = df[[h, l, c]].astype(float).copy()
    prev_close = d[c].shift(1)
    tr = (d[h] - d[l]).abs()
    tr = pd.concat([tr, (d[h] - prev_close).abs(), (d[l] - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    return float(atr.iloc[-1]) if len(atr) >= n and pd.notna(atr.iloc[-1]) else 0.0


def _donchian(df: pd.DataFrame, h: str, l: str, n: int = 20) -> tuple[float, float]:
    up = df[h].rolling(n).max().shift(1)
    dn = df[l].rolling(n).min().shift(1)
    up_v = float(up.iloc[-1]) if len(up) >= n and pd.notna(up.iloc[-1]) else 0.0
    dn_v = float(dn.iloc[-1]) if len(dn) >= n and pd.notna(dn.iloc[-1]) else 0.0
    return up_v, dn_v


def _h3_l3(df: pd.DataFrame, h: str, l: str) -> tuple[float, float]:
    h3 = df[h].rolling(3).max()
    l3 = df[l].rolling(3).min()
    return (
        float(h3.iloc[-1]) if pd.notna(h3.iloc[-1]) else 0.0,
        float(l3.iloc[-1]) if pd.notna(l3.iloc[-1]) else 0.0,
    )


def build_user_message(etf_code: str, df: pd.DataFrame) -> str:
    """构建用户消息，兼容不同列名版本；补充 ATR/Donchian/H3L3 指标"""
    df = df.copy()

    close_col = _safe_col(df, ["收盘", "收盘价", "close", "Close"])
    volume_col = _safe_col(df, ["成交量", "volume", "Volume"])
    name_col = _safe_col(df, ["名称", "name", "证券简称", "基金简称"])  # 可能缺失
    high_col = _safe_col(df, ["最高", "最高价", "high", "High"])
    low_col = _safe_col(df, ["最低", "最低价", "low", "Low"])

    if close_col is None:
        raise KeyError("数据缺少收盘价列（收盘/收盘价/close）")
    if volume_col is None:
        df["成交量(估)"] = 0
        volume_col = "成交量(估)"

    rolling20 = df[close_col].rolling(window=20).mean()
    rolling60 = df[close_col].rolling(window=60).mean()
    ma20 = float(rolling20.iloc[-1]) if not pd.isna(rolling20.iloc[-1]) else 0.0
    ma60 = float(rolling60.iloc[-1]) if not pd.isna(rolling60.iloc[-1]) else 0.0
    trend = "上涨趋势" if ma20 > ma60 else ("下跌趋势" if ma20 < ma60 else "震荡趋势")

    latest = df.iloc[-1]
    close_price = float(latest[close_col])
    volume_val = float(latest[volume_col]) if volume_col in latest else 0.0

    # 量能变化
    vol5 = df[volume_col].rolling(window=5).mean()
    vol_change = 0.0
    if len(df) >= 6 and not pd.isna(vol5.iloc[-2]) and vol5.iloc[-2] != 0:
        vol_change = float(volume_val / vol5.iloc[-2] - 1)
    vol_status = (
        "成交量显著放大" if vol_change > 0.3 else ("成交量显著萎缩" if vol_change < -0.3 else "成交量正常")
    )

    # 涨跌与波动率
    recent5 = float(((df[close_col].iloc[-1] / df[close_col].iloc[-5]) - 1) * 100) if len(df) >= 5 else 0.0
    vol20 = float(df[close_col].pct_change().rolling(window=20).std().iloc[-1] * 100) if len(df) >= 20 else 0.0

    # 新增：ATR / Donchian / H3L3（缺列则回退0）
    atr14 = _atr(df, high_col, low_col, close_col, 14) if high_col and low_col else 0.0
    dc_up, dc_dn = _donchian(df, high_col, low_col, 20) if high_col and low_col else (0.0, 0.0)
    h3, l3 = _h3_l3(df, high_col, low_col) if high_col and low_col else (0.0, 0.0)

    date_str = str(latest.get("日期", latest.name))
    name_str = str(latest.get(name_col, "未知")) if name_col else "未知"

    message = f"""
## ETF信息
- 代码: {etf_code}
- 名称: {name_str}

## 最新价格数据
- 日期: {date_str}
- 收盘价: {close_price:.4f}
- 成交量: {volume_val:.0f} ({vol_status})

## 技术指标
- MA20: {ma20:.4f} | MA60: {ma60:.4f} | 趋势: {trend}
- ATR(14): {atr14:.4f}
- Donchian(20) 阻力/支撑: {dc_up:.4f} / {dc_dn:.4f}
- H3/L3(3日高低): {h3:.4f} / {l3:.4f}
- 价格位置: {'高于MA20，偏强' if close_price > ma20 else '低于MA20，偏弱'}

## 历史数据统计
- 最近5日涨跌幅: {recent5:.2f}%
- 最近20日波动率: {vol20:.2f}%

## 任务
基于以上数据，分析{etf_code}的走势，决定买入/卖出/持有。严格输出JSON：
{{"decision":"buy|sell|hold","confidence":0-1,"reasoning":"50-100字","target_price":数值或null,"stop_loss":数值或null,"take_profit":数值或null}}
"""
    return message

