# -*- coding: utf-8 -*-
"""
交易执行模块（增强版）：
- 虚拟账户，初始资金可配置（默认10万）
- 下单规则：按AI决策，支持动态仓位（基于置信度）
- 风控：止损/止盈 + 跟踪止损（高水位）
- 成本与滑点：支持在 .env 中配置（基点bps）
- 记录交易到 SQLite: data/trade_history.db

.env 开关（可选）：
- ENABLE_DYNAMIC_POSITION=true/false（默认false）
- BASE_POSITION_PCT=0.2（基础仓位比例）
- MIN_POSITION_PCT=0.05（最小仓位）
- MAX_POSITION_PCT=0.3（最大仓位）
- ENABLE_TRAILING_STOP=true/false（默认false）
- TRAILING_STOP_PCT=0.05（高水位回撤5%触发止损）
- TRAILING_STEP_PCT=0.01（价格每上涨1%更新一次高水位）
- COST_BPS=5（万分之5 作为交易手续费或成本）
- SLIPPAGE_BPS=2（成交价滑点，买入加、卖出减）
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Dict, Any

from dotenv import load_dotenv


class TradeExecutor:
    def __init__(self, initial_capital: float = 100000.0, db_path: str | None = None) -> None:
        load_dotenv(override=True)
        self.capital = float(initial_capital)
        # positions: {etf_code: {quantity, entry_price, date, stop_loss, take_profit, high_watermark}}
        self.positions: Dict[str, Dict[str, Any]] = {}
        if db_path is None:
            db_path = self._default_db_path()
        self.db_path = db_path
        self._ensure_dir(os.path.dirname(self.db_path))
        self._init_db()

        # --- env configs ---
        self.enable_dyn_pos = os.getenv("ENABLE_DYNAMIC_POSITION", "false").lower() == "true"
        self.base_pos = float(os.getenv("BASE_POSITION_PCT", "0.2"))
        self.min_pos = float(os.getenv("MIN_POSITION_PCT", "0.05"))
        self.max_pos = float(os.getenv("MAX_POSITION_PCT", "0.3"))

        self.enable_trailing = os.getenv("ENABLE_TRAILING_STOP", "false").lower() == "true"
        self.trailing_pct = float(os.getenv("TRAILING_STOP_PCT", "0.05"))
        self.trailing_step = float(os.getenv("TRAILING_STEP_PCT", "0.01"))

        self.cost_bps = float(os.getenv("COST_BPS", "5"))  # 0.05%
        self.slippage_bps = float(os.getenv("SLIPPAGE_BPS", "2"))  # 0.02%

        self.force_trade_timestamp: Optional[datetime] = None

        # --- New Strategy Params ---
        self.hard_sl_pct = float(os.getenv("HARD_STOP_LOSS_PCT", "0.0"))
        self.quick_tp_trigger = float(os.getenv("QUICK_TAKE_PROFIT_TRIGGER", "0.0"))
        self.quick_tp_sell_ratio = float(os.getenv("QUICK_TAKE_PROFIT_SELL_RATIO", "0.0"))

    @staticmethod
    def _project_root() -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    @staticmethod
    def _ensure_dir(p: str) -> None:
        os.makedirs(p, exist_ok=True)

    def _default_db_path(self) -> str:
        data_dir = os.path.join(self._project_root(), "data")
        self._ensure_dir(data_dir)
        return os.path.join(data_dir, "trade_history.db")

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    etf_code TEXT,
                    action TEXT,
                    price REAL,
                    quantity REAL,
                    value REAL,
                    capital_after REAL,
                    reasoning TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    # ---------------- helpers ----------------
    def _clamp(self, v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    def _position_pct(self, decision: Dict[str, Any]) -> float:
        # 允许外部传入 position_pct 覆盖（例如按波动率调整后的仓位），再做安全夹取
        override = decision.get("position_pct")
        if override is not None:
            try:
                pct = float(override)
                return self._clamp(pct, self.min_pos, self.max_pos)
            except Exception:
                pass
        pct = self.base_pos
        if self.enable_dyn_pos:
            conf = float(decision.get("confidence", 0.5) or 0.5)  # [0,1]
            # 简单线性缩放：base * (0.5 + 0.5*conf)
            pct = self.base_pos * (0.5 + 0.5 * conf)
        return self._clamp(pct, self.min_pos, self.max_pos)

    def _buy_exec_price(self, px: float) -> float:
        return float(px) * (1.0 + self.slippage_bps / 10000.0)

    def _sell_exec_price(self, px: float) -> float:
        return float(px) * (1.0 - self.slippage_bps / 10000.0)

    def _cost_amount(self, gross_value: float) -> float:
        return float(gross_value) * (self.cost_bps / 10000.0)

    def _update_trailing(self, etf_code: str, current_price: float) -> None:
        if not self.enable_trailing:
            return
        if etf_code not in self.positions:
            return
        pos = self.positions[etf_code]
        px = float(current_price)
        hw = float(pos.get("high_watermark", pos.get("entry_price", px)))
        # 若价格上涨超过 step，更新高水位
        if px >= hw * (1.0 + self.trailing_step):
            hw = px
            pos["high_watermark"] = hw
            # 动态止损设为高水位下的 trailing_pct 距离
            dyn_sl = hw * (1.0 - self.trailing_pct)
            # 不降低已经存在的止损（仅上调）
            if pos.get("stop_loss") is None or dyn_sl > float(pos.get("stop_loss")):
                pos["stop_loss"] = dyn_sl

    # ---------------- core ----------------
    def execute_trade(self, etf_code: str, decision: Dict[str, Any], current_price: float) -> float:
        """根据决策执行交易，并记录到数据库。返回交易后现金余额。
        - buy: 建仓并记录止损/止盈（若提供），按动态仓位与滑点/成本计算
        - sell: 卖出现有仓位，考虑滑点/成本
        - hold: 不操作
        """
        action = str(decision.get("decision", "hold")).lower()
        reasoning = str(decision.get("reasoning", ""))
        stop_loss = decision.get("stop_loss")
        take_profit = decision.get("take_profit")
        now_str = (
            self.force_trade_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if self.force_trade_timestamp
            else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        conn = sqlite3.connect(self.db_path)
        try:
            if action == "buy" and etf_code not in self.positions:
                pos_pct = self._position_pct(decision)
                exec_px = self._buy_exec_price(current_price)
                if exec_px <= 0:
                    return self.capital
                budget = self.capital * pos_pct
                quantity = budget / exec_px
                gross_value = quantity * exec_px
                cost = self._cost_amount(gross_value)
                total_out = gross_value + cost
                if total_out <= self.capital and quantity > 0:
                    self.capital -= total_out
                    self.positions[etf_code] = {
                        "quantity": float(quantity),
                        "entry_price": float(exec_px),
                        "date": now_str,
                        "stop_loss": float(stop_loss) if stop_loss else None,
                        "take_profit": float(take_profit) if take_profit else None,
                        "high_watermark": float(exec_px),
                    }
                    note = reasoning + f" | 动态仓位: {pos_pct:.2%}, 滑点买价: {exec_px:.4f}, 成本: {cost:.2f}"
                    conn.execute(
                        "INSERT INTO trades (date, etf_code, action, price, quantity, value, capital_after, reasoning)\n                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (now_str, etf_code, "buy", float(exec_px), float(quantity), float(gross_value), float(self.capital), note),
                    )
                    conn.commit()

            elif action == "sell" and etf_code in self.positions:
                # 允许部分卖出，通过 decision.sell_ratio 控制
                sell_ratio = float(decision.get("sell_ratio", 1.0)) # 默认100%
                pos = self.positions[etf_code]
                quantity_to_sell = float(pos["quantity"]) * sell_ratio

                if quantity_to_sell <= 1e-9:
                    return self.capital

                exec_px = self._sell_exec_price(current_price)
                gross_value = quantity_to_sell * exec_px
                cost = self._cost_amount(gross_value)
                net_in = gross_value - cost
                self.capital += net_in

                note = reasoning + f" | 卖出比例: {sell_ratio:.2%}, 滑点卖价: {exec_px:.4f}, 成本: {cost:.2f}"
                conn.execute(
                    "INSERT INTO trades (date, etf_code, action, price, quantity, value, capital_after, reasoning)\n                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (now_str, etf_code, "sell", float(exec_px), float(quantity_to_sell), float(gross_value), float(self.capital), note),
                )
                conn.commit()

                # 更新或删除持仓（仅一次卖出，不再二次卖出剩余）
                if sell_ratio >= 0.9999:
                    if etf_code in self.positions:
                        del self.positions[etf_code]
                else:
                    pos["quantity"] = float(pos["quantity"]) - float(quantity_to_sell)
                    if pos["quantity"] <= 1e-9:
                        del self.positions[etf_code]

            else:
                # hold 或无法卖出/买入
                pass
        finally:
            conn.close()

        return self.capital

    def risk_check_and_force_sell(self, etf_code: str, current_price: float) -> bool:
        """若触发止损/止盈或跟踪止损则强制卖出，返回是否卖出。"""
        if etf_code not in self.positions:
            return False
        # 先更新跟踪止损
        self._update_trailing(etf_code, current_price)
        pos = self.positions[etf_code]
        sl = pos.get("stop_loss")
        tp = pos.get("take_profit")
        reason = None
        px = float(current_price)
        if sl is not None and px <= float(sl):
            reason = f"触发止损({sl:.4f})"
        if tp is not None and px >= float(tp):
            # 若同时触发，以止盈为先
            reason = f"触发止盈({tp:.4f})"
        if reason is None:
            return False

        now_str = (
            self.force_trade_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if self.force_trade_timestamp
            else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        quantity = float(pos.get("quantity", 0))
        if quantity <= 0:
            return False
        exec_px = self._sell_exec_price(px)
        gross_value = quantity * exec_px
        cost = self._cost_amount(gross_value)
        net_in = gross_value - cost

        conn = sqlite3.connect(self.db_path)
        try:
            self.capital += net_in
            note = reason + f" | 滑点卖价: {exec_px:.4f}, 成本: {cost:.2f}"
            conn.execute(
                "INSERT INTO trades (date, etf_code, action, price, quantity, value, capital_after, reasoning)\n                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now_str, etf_code, "sell", float(exec_px), float(quantity), float(gross_value), float(self.capital), note),
            )
            conn.commit()
            del self.positions[etf_code]
            return True
        finally:
            conn.close()

    def auto_risk_sell(self, current_prices: Dict[str, float]) -> int:
        """遍历当前持仓，按当前价格执行（跟踪）止损/止盈、快速止盈、强制止损。返回卖出笔数。"""
        count = 0
        for code in list(self.positions.keys()):
            px = float(current_prices.get(code, 0) or 0)
            if px <= 0:
                continue

            pos = self.positions.get(code)
            if not pos:
                continue

            entry_price = float(pos.get("entry_price", px))
            pnl_ratio = (px - entry_price) / entry_price if entry_price > 0 else 0.0

            # 1. 强制止损 (最高优先级)
            if self.hard_sl_pct > 0 and pnl_ratio <= -self.hard_sl_pct:
                decision = {"decision": "sell", "sell_ratio": 1.0, "reasoning": f"强制止损({-self.hard_sl_pct:.2%})"}
                self.execute_trade(code, decision, px)
                count += 1
                continue # 已清仓，不再检查其他规则

            # 2. 快速止盈 (部分卖出)
            if self.quick_tp_trigger > 0 and pnl_ratio >= self.quick_tp_trigger and not pos.get("quick_tp_done", False):
                decision = {"decision": "sell", "sell_ratio": self.quick_tp_sell_ratio, "reasoning": f"快速止盈({self.quick_tp_trigger:.2%})"}
                self.execute_trade(code, decision, px)
                pos["quick_tp_done"] = True # 标记已执行，避免重复触发
                count += 1
                # 注意：部分止盈后，剩余仓位仍可触发其他卖出规则

            # 3. AI定义的止损/止盈或跟踪止损
            if self.risk_check_and_force_sell(code, px):
                count += 1

        return count

    def restore_state_from_db(self, as_of_date: Optional[str] = None) -> None:
        """从交易历史恢复截至 as_of_date 的现金和持仓, 包括平均持仓成本。"""
        import logging
        import pandas as pd

        conn = sqlite3.connect(self.db_path)
        try:
            q = "SELECT date, etf_code, action, price, quantity, capital_after FROM trades ORDER BY datetime(date)"
            df = pd.read_sql_query(q, conn)
        finally:
            conn.close()

        if df.empty:
            return

        if as_of_date:
            df["dt"] = pd.to_datetime(df["date"], errors="coerce")
            cutoff = pd.to_datetime(as_of_date)
            df = df[df["dt"] < cutoff]

        if df.empty:
            return

        if df["capital_after"].notna().any():
            self.capital = float(df["capital_after"].dropna().iloc[-1])

        temp_positions: Dict[str, Dict[str, float]] = {}
        for _, r in df.iterrows():
            code = str(r["etf_code"]).strip()
            act = str(r["action"]).lower()
            qty = float(r.get("quantity", 0) or 0)
            price = float(r.get("price", 0) or 0)
            
            if not code or code == 'ADJ':
                continue

            if act == "buy":
                if code not in temp_positions:
                    temp_positions[code] = {"quantity": 0, "cost_basis": 0}
                
                temp_positions[code]["quantity"] += qty
                temp_positions[code]["cost_basis"] += qty * price

            elif act == "sell":
                if code in temp_positions and temp_positions[code]["quantity"] > 1e-9:
                    avg_price = temp_positions[code]["cost_basis"] / temp_positions[code]["quantity"]
                    temp_positions[code]["quantity"] -= qty
                    temp_positions[code]["cost_basis"] -= qty * avg_price
                    if temp_positions[code]["quantity"] < 1e-9:
                        del temp_positions[code]
        
        self.positions = {}
        for code, data in temp_positions.items():
            quantity = data["quantity"]
            cost_basis = data["cost_basis"]
            if quantity > 1e-9:
                avg_price = cost_basis / quantity
                self.positions[code] = {
                    "quantity": quantity,
                    "entry_price": avg_price,
                    "date": None, 
                    "stop_loss": None,
                    "take_profit": None,
                    "high_watermark": avg_price,
                }
        
        logging.info(f"已从交易历史恢复账户：现金{self.capital:.2f}，持仓标的{len(self.positions)}")

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        total_value = float(self.capital)
        for etf_code, pos in self.positions.items():
            px = float(current_prices.get(etf_code, 0))
            total_value += float(pos.get("quantity", 0)) * (px if px > 0 else 0)
        return total_value

