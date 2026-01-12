# -*- coding: utf-8 -*-
"""
绩效评估：读取交易数据，计算核心指标
- 交易次数：买入次数 + 卖出次数（各自分别统计）
- 胜率（仅以卖出成交作为一笔交易结算：卖出且盈利的次数 / 卖出次数）
- 总收益率、年化收益率
- 最大回撤
"""
from __future__ import annotations

import os
from typing import Dict, Any

import numpy as np
import pandas as pd


def calculate_performance_from_data(trades_df: pd.DataFrame | None, daily_perf_df: pd.DataFrame | None) -> Dict[str, Any]:
    """Calculates performance metrics from provided dataframes."""
    base_empty = {
        "total_trades": 0,
        "buy_count": 0,
        "sell_count": 0,
        "win_rate": 0.0,
        "total_return": 0.0,
        "annualized_return": 0.0,
        "max_drawdown": 0.0,
    }

    if trades_df is None or trades_df.empty:
        return dict(base_empty)

    # --- Trade-based metrics ---
    trades_df["action"] = trades_df["action"].astype(str).str.lower()
    buy_count = int((trades_df["action"] == "buy").sum())
    sell_count = int((trades_df["action"] == "sell").sum())
    total_trades = buy_count + sell_count

    # --- Win rate calculation (FIFO pairing) ---
    win_sell = 0
    total_sell = 0
    holdings_cost: dict[str, float] = {}
    holdings_qty: dict[str, float] = {}

    for _, row in trades_df.sort_values("date").iterrows():
        code = str(row.get("etf_code", ""))
        if not code:
            continue
        qty = float(row.get("quantity", 0) or 0)
        price = float(row.get("price", 0) or 0)
        action = str(row.get("action", "").lower())
        if action == "buy":
            # update avg cost
            prev_qty = holdings_qty.get(code, 0.0)
            prev_cost = holdings_cost.get(code, 0.0)
            new_qty = prev_qty + qty
            if new_qty > 1e-9:
                avg_cost = (prev_cost * prev_qty + price * qty) / new_qty
                holdings_qty[code] = new_qty
                holdings_cost[code] = avg_cost
        elif action == "sell":
            prev_qty = holdings_qty.get(code, 0.0)
            if prev_qty <= 1e-9:
                continue  # nothing to match
            sell_qty = min(prev_qty, qty)
            avg_cost = holdings_cost.get(code, price)
            profit = (price - avg_cost) * sell_qty
            total_sell += 1
            if profit > 0:
                win_sell += 1
            holdings_qty[code] = prev_qty - sell_qty
            if holdings_qty[code] <= 1e-9:
                holdings_cost.pop(code, None)
                holdings_qty.pop(code, None)

    win_rate = (win_sell / total_sell) if total_sell else 0.0

    # --- Equity-based metrics ---
    if daily_perf_df is None or daily_perf_df.empty:
        out = dict(base_empty)
        out.update({
            "total_trades": total_trades,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "win_rate": win_rate * 100.0,
        })
        return out

    equity = daily_perf_df["total_assets"].astype(float)
    dates = pd.to_datetime(daily_perf_df["date"])

    if len(equity) < 2:
        return dict(base_empty)

    initial_capital = equity.iloc[0]
    final_capital = equity.iloc[-1]
    
    total_return = (final_capital - initial_capital) / initial_capital if initial_capital else 0.0

    days = max((dates.iloc[-1] - dates.iloc[0]).days, 1)
    annualized_return = total_return * (365.0 / days) if days > 0 else 0.0

    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_drawdown = float(drawdown.min()) if len(drawdown) > 0 else 0.0

    return {
        "total_trades": total_trades,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "win_rate": win_rate * 100.0, # Remains 0.0 based on placeholder
        "total_return": total_return * 100.0,
        "annualized_return": annualized_return * 100.0,
        "max_drawdown": max_drawdown * 100.0,
    }
