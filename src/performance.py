# -*- coding: utf-8 -*-
"""
绩效评估：读取交易数据库，计算核心指标
- 总交易次数（卖出次数计为完成一笔交易）
- 胜率（卖出且盈利的次数 / 卖出次数）
- 总收益率、年化收益率
- 最大回撤
"""
from __future__ import annotations

import os
import sqlite3
from typing import Dict, Any

import numpy as np
import pandas as pd


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _db_path() -> str:
    return os.path.join(_project_root(), "data", "trade_history.db")


def calculate_performance(db_path: str | None = None) -> Dict[str, Any]:
    if db_path is None:
        db_path = _db_path()

    if not os.path.exists(db_path):
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_return": 0.0,
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
        }

    conn = sqlite3.connect(db_path)
    try:
        trades = pd.read_sql_query("SELECT * FROM trades ORDER BY datetime(date)", conn)
    finally:
        conn.close()

    if trades.empty:
        # 尝试用 daily_equity 作为回退计算收益类指标
        try:
            conn = sqlite3.connect(db_path)
            deq = pd.read_sql_query("SELECT date, equity FROM daily_equity ORDER BY date", conn)
            conn.close()
        except Exception:
            deq = pd.DataFrame()
        if not deq.empty:
            deq["date"] = pd.to_datetime(deq["date"])  # 纯日期
            equity = deq["equity"].astype(float).values
            if len(equity) >= 2:
                first, last = float(equity[0]), float(equity[-1])
                total_return = (last - first) / (first if first else 1.0)
                days = max((deq["date"].iloc[-1] - deq["date"].iloc[0]).days, 1)
                annualized_return = total_return * (365.0 / days) if days > 0 else 0.0
                peak = np.maximum.accumulate(equity)
                drawdown = (equity - peak) / peak
                max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0
                return {
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "total_return": total_return * 100.0,
                    "annualized_return": annualized_return * 100.0,
                    "max_drawdown": max_drawdown * 100.0,
                }
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_return": 0.0,
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
        }

    trades["date"] = pd.to_datetime(trades["date"])  # with time
    # 定义每笔交易盈亏：卖出时 +value，买入时 -value
    trades["profit"] = trades.apply(lambda r: r["value"] if r["action"] == "sell" else -r["value"], axis=1)

    total_trades = int((trades["action"] == "sell").sum())
    win_trades = int(((trades["action"] == "sell") & (trades["profit"] > 0)).sum())
    win_rate = (win_trades / total_trades) if total_trades > 0 else 0.0

    initial_capital = float(trades["capital_after"].iloc[0] if len(trades) > 0 else 100000.0)
    final_capital = float(trades["capital_after"].iloc[-1])
    total_return = (final_capital - initial_capital) / (initial_capital if initial_capital else 1.0)

    days = max((trades["date"].iloc[-1] - trades["date"].iloc[0]).days, 1)
    annualized_return = total_return * (365.0 / days) if days > 0 else 0.0

    # 最大回撤（基于capital_after）
    equity = trades["capital_after"].astype(float).values
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0

    return {
        "total_trades": total_trades,
        "win_rate": win_rate * 100.0,
        "total_return": total_return * 100.0,
        "annualized_return": annualized_return * 100.0,
        "max_drawdown": max_drawdown * 100.0,
    }


if __name__ == "__main__":
    perf = calculate_performance()
    print("=== 投资绩效 ===")
    print(f"总交易次数: {perf['total_trades']}")
    print(f"胜率: {perf['win_rate']:.2f}%")
    print(f"总收益率: {perf['total_return']:.2f}%")
    print(f"年化收益率: {perf['annualized_return']:.2f}%")
    print(f"最大回撤: {perf['max_drawdown']:.2f}%")

