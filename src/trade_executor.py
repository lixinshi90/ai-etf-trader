# -*- coding: utf-8 -*-
"""
交易执行模块（增强版）：
- 虚拟账户，初始资金可配置（默认10万）
- 下单规则：按AI决策，支持动态仓位（基于置信度）
- 风控：止损/止盈 + 跟踪止损（高水位）
- 成本与滑点：改为读取 config.yaml（买卖分别配置）
- 记录交易到 SQLite: data/trade_history.db

环境变量（可选，覆盖部分行为）：
- ENABLE_DYNAMIC_POSITION=true/false（默认false）
- BASE_POSITION_PCT=0.2（基础仓位比例）
- MIN_POSITION_PCT=0.05（最小仓位）
- MAX_POSITION_PCT=0.3（动态仓位的软上限；硬上限取自 config.yaml 的 max_position_pct）
- ENABLE_TRAILING_STOP=true/false（默认false）
- TRAILING_STOP_PCT=0.05（高水位回撤5%触发止损）
- TRAILING_STEP_PCT=0.01（价格每上涨1%更新一次高水位）
- HARD_STOP_LOSS_PCT=0.0（强制止损阈值，0为关闭）
- QUICK_TAKE_PROFIT_TRIGGER=0.0（快速止盈触发阈值，0为关闭）
- QUICK_TAKE_PROFIT_SELL_RATIO=0.0（快速止盈卖出比例）
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional

import yaml
from dotenv import load_dotenv

from .equity_anchor import anchor_account_to_corrected_equity


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

        # --- Load config.yaml (for costs & hard position cap) ---
        cfg = self._load_config()
        st = cfg.get('strategy', {}) if isinstance(cfg, dict) else {}
        costs = cfg.get('costs', {}) if isinstance(cfg, dict) else {}
        # 硬性单笔买入上限（相对于当前现金）
        self.max_single_trade_pct = float(st.get('max_position_pct', 0.20))
        # 成本参数（买入：滑点+佣金；卖出：滑点+佣金+印花税）
        self.buy_slippage = float(costs.get('buy_slippage', 0.001))
        self.buy_commission = float(costs.get('buy_commission', 0.0005))
        self.sell_slippage = float(costs.get('sell_slippage', 0.001))
        self.sell_commission = float(costs.get('sell_commission', 0.0005))
        self.sell_tax = float(costs.get('sell_tax', 0.001))

        # --- env configs (dynamic position / trailing) ---
        self.enable_dyn_pos = os.getenv("ENABLE_DYNAMIC_POSITION", "false").lower() == "true"
        self.base_pos = float(os.getenv("BASE_POSITION_PCT", "0.2"))
        self.min_pos = float(os.getenv("MIN_POSITION_PCT", "0.05"))
        self.max_pos = float(os.getenv("MAX_POSITION_PCT", "0.3"))  # 仅用于动态仓位软上限

        self.enable_trailing = os.getenv("ENABLE_TRAILING_STOP", "false").lower() == "true"
        self.trailing_pct = float(os.getenv("TRAILING_STOP_PCT", "0.05"))
        self.trailing_step = float(os.getenv("TRAILING_STEP_PCT", "0.01"))

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

    def _load_config(self) -> dict:
        cfg_path = os.path.join(self._project_root(), "config.yaml")
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

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
        # 与审计逻辑对齐：不修改成交价，滑点体现在成本里
        return float(px)

    def _sell_exec_price(self, px: float) -> float:
        # 与审计逻辑对齐：不修改成交价，滑点体现在成本里
        return float(px)

    def _buy_cost_amount(self, gross_value: float) -> float:
        return float(gross_value) * (self.buy_slippage + self.buy_commission)

    def _sell_cost_amount(self, gross_value: float) -> float:
        return float(gross_value) * (self.sell_slippage + self.sell_commission + self.sell_tax)

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
    def execute_trade(self, etf_code: str, decision: Dict[str, Any], current_price: float, current_prices: Dict[str, float]) -> float:
        """根据决策执行交易，并记录到数据库。返回交易后现金余额。
        - buy: 建仓并记录止损/止盈（若提供），按动态仓位与成本计算，且施加20%单笔与现金约束
        - sell: 卖出现有仓位，考虑成本
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
            if action == "buy":
                # --- 1. 计算本次交易预算（与之前逻辑类似） ---
                pos_pct = self._position_pct(decision)
                budget = self.capital * pos_pct
                max_buy_value_single = self.capital * self.max_single_trade_pct
                total_cost_rate = 1.0 + self.buy_slippage + self.buy_commission
                max_buy_value_cash = self.capital / total_cost_rate if total_cost_rate > 0 else self.capital
                buy_value = min(budget, max_buy_value_single, max_buy_value_cash)

                # --- 2. 新增：总仓位上限约束（允许加仓的核心风控） ---
                total_equity = self.get_portfolio_value(current_prices)
                existing_value = 0.0
                if etf_code in self.positions:
                    existing_qty = float(self.positions[etf_code].get('quantity', 0))
                    existing_value = existing_qty * current_price
                
                # max_pos 是总仓位比例上限 (e.g., 0.3 for 30%)
                max_total_pos_value = total_equity * self.max_pos
                allowed_additional_value = max(0, max_total_pos_value - existing_value)

                if buy_value > allowed_additional_value:
                    reasoning += f" | 触发总仓位上限({self.max_pos*100:.0f}%)，加仓额度从 {buy_value:.2f} 调整至 {allowed_additional_value:.2f}"
                    buy_value = allowed_additional_value

                # --- 3. 执行交易 ---
                exec_px = self._buy_exec_price(current_price)
                if exec_px <= 0 or buy_value <= 1e-9: # 最小交易金额
                    return self.capital

                quantity = buy_value / exec_px
                gross_value = quantity * exec_px
                cost = self._buy_cost_amount(gross_value)
                total_out = gross_value + cost

                if total_out <= self.capital and quantity > 0:
                    self.capital -= total_out
                    
                    # --- 4. 更新持仓（支持加仓） ---
                    if etf_code in self.positions:
                        # 加仓：更新数量和平均成本
                        pos = self.positions[etf_code]
                        old_qty = float(pos.get('quantity', 0))
                        old_cost_basis = old_qty * float(pos.get('entry_price', 0))
                        
                        new_qty = old_qty + quantity
                        new_cost_basis = old_cost_basis + gross_value
                        new_avg_price = new_cost_basis / new_qty if new_qty > 0 else 0
                        
                        pos['quantity'] = new_qty
                        pos['entry_price'] = new_avg_price
                        pos['high_watermark'] = max(float(pos.get('high_watermark', 0)), exec_px)
                        reasoning += " (加仓)"
                    else:
                        # 开新仓
                        self.positions[etf_code] = {
                            "quantity": float(quantity),
                            "entry_price": float(exec_px),
                            "date": now_str,
                            "stop_loss": float(stop_loss) if stop_loss else None,
                            "take_profit": float(take_profit) if take_profit else None,
                            "high_watermark": float(exec_px),
                        }

                    # --- 5. 记录交易 ---
                    note = reasoning + f" | 动态仓位: {pos_pct:.2%}, 成本: {cost:.2f}"
                    conn.execute(
                        "INSERT INTO trades (date, etf_code, action, price, quantity, value, capital_after, reasoning)\n                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (now_str, etf_code, "buy", float(exec_px), float(quantity), float(gross_value), float(self.capital), note),
                    )
                    conn.commit()

            elif action == "sell" and etf_code in self.positions:
                # 允许部分卖出，通过 decision.sell_ratio 控制
                sell_ratio = float(decision.get("sell_ratio", 1.0))  # 默认100%
                pos = self.positions[etf_code]
                quantity_to_sell = float(pos["quantity"]) * sell_ratio

                if quantity_to_sell <= 1e-9:
                    return self.capital

                exec_px = self._sell_exec_price(current_price)
                gross_value = quantity_to_sell * exec_px
                cost = self._sell_cost_amount(gross_value)
                net_in = gross_value - cost
                self.capital += net_in

                note = reasoning + f" | 卖出比例: {sell_ratio:.2%}, 成本: {cost:.2f}"
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
        cost = self._sell_cost_amount(gross_value)
        net_in = gross_value - cost

        conn = sqlite3.connect(self.db_path)
        try:
            self.capital += net_in
            note = reason + f" | 成本: {cost:.2f}"
            conn.execute(
                "INSERT INTO trades (date, etf_code, action, price, quantity, value, capital_after, reasoning)\n                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now_str, etf_code, "sell", float(exec_px), float(quantity), float(gross_value), float(self.capital), note),
            )
            conn.commit()
            del self.positions[etf_code]
            return True
        finally:
            conn.close()

    def auto_risk_sell(self, current_prices: Dict[str, float], latest_dfs: Dict[str, Any]) -> int:
        """遍历当前持仓，按当前价格执行（跟踪）止损/止盈、快速止盈、强制止损。返回卖出笔数。
        注意：已移除“持仓满10日，强制平仓”的时间型规则。
        """
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

            # --- Mandatory Sell Rules ---
            sell_executed = False
            if self.quick_tp_trigger > 0 and pnl_ratio >= self.quick_tp_trigger and not pos.get("quick_tp_done", False):
                decision = {"decision": "sell", "sell_ratio": self.quick_tp_sell_ratio, "reasoning": f"快速止盈({self.quick_tp_trigger:.2%})"}
                self.execute_trade(code, decision, px, current_prices)
                pos["quick_tp_done"] = True
                count += 1
                sell_executed = True

            if sell_executed:
                continue  # 下一只

            if self.hard_sl_pct > 0 and pnl_ratio <= -self.hard_sl_pct:
                decision = {"decision": "sell", "sell_ratio": 1.0, "reasoning": f"强制止损({-self.hard_sl_pct:.2%})"}
                self.execute_trade(code, decision, px, current_prices)
                count += 1
                continue

            # 3. AI定义的SL/TP或跟踪止损
            if self.risk_check_and_force_sell(code, px):
                count += 1

        return count

    def restore_state_from_db(self, as_of_date: Optional[str] = None) -> None:
        """从交易历史恢复截至 as_of_date 的现金和持仓。
        采用与 replay_guard 一致的“完整回放”逻辑，确保口径统一。
        """
        import logging
        import pandas as pd
        import re

        conn = sqlite3.connect(self.db_path)
        try:
            # 必须包含 reasoning 以解析成本
            q = "SELECT date, etf_code, action, price, quantity, value, capital_after, reasoning FROM trades ORDER BY datetime(date)"
            df = pd.read_sql_query(q, conn)
        finally:
            conn.close()

        if df.empty:
            logging.info("交易历史为空，从初始资金开始。")
            self.capital = float(os.getenv('INITIAL_CAPITAL', '100000'))
            self.positions = {}
            return

        if as_of_date:
            df["dt"] = pd.to_datetime(df["date"], errors="coerce")
            cutoff = pd.to_datetime(as_of_date)
            df = df[df["dt"] < cutoff]

        if df.empty:
            logging.info(f"截至 {as_of_date} 无交易历史，从初始资金开始。")
            self.capital = float(os.getenv('INITIAL_CAPITAL', '100000'))
            self.positions = {}
            return

        # --- 1. 推断回放起始现金 ---
        default_ic = float(os.getenv('INITIAL_CAPITAL', '100000'))
        inferred_ic = default_ic
        try:
            first = df.iloc[0]
            first_act = str(first.get('action') or '').lower()
            first_gross = float(first.get('value') or 0.0)
            first_cap_after = float(first.get('capital_after') or 0.0) if 'capital_after' in df.columns else None
            first_reason = str(first.get('reasoning') or '')

            first_cost = 0.0
            m0 = re.search(r"成本:\s*([0-9]+(?:\.[0-9]+)?)", first_reason)
            if m0:
                first_cost = float(m0.group(1))

            if first_cap_after is not None and first_cap_after > 0 and first_gross > 0 and first_act in ('buy','sell'):
                if first_act == 'buy':
                    inferred_ic = float(first_cap_after) + float(first_gross) + float(first_cost)
                else:
                    inferred_ic = float(first_cap_after) - float(first_gross) + float(first_cost)
        except Exception as e:
            logging.warning(f"[restore] 推断初始现金失败，回退到 INITIAL_CAPITAL: {e}")

        # --- 2. 完整回放计算最终现金与持仓 ---
        current_cash = inferred_ic
        temp_positions: Dict[str, Dict[str, float]] = {}

        for _, r in df.iterrows():
            code = str(r["etf_code"]).strip()
            act = str(r["action"]).lower()
            qty = float(r.get("quantity", 0) or 0)
            gross = float(r.get("value") or 0.0)
            reason = str(r.get("reasoning") or "")

            cost = 0.0
            m = re.search(r"成本:\s*([0-9]+(?:\.[0-9]+)?)", reason)
            if m:
                cost = float(m.group(1))

            if not code or code == 'ADJ': continue

            if act == "buy":
                current_cash -= (gross + cost)
                if code not in temp_positions:
                    temp_positions[code] = {"quantity": 0, "cost_basis": 0}
                temp_positions[code]["quantity"] += qty
                temp_positions[code]["cost_basis"] += gross # cost_basis is pre-cost

            elif act == "sell":
                current_cash += (gross - cost)
                if code in temp_positions and temp_positions[code]["quantity"] > 1e-9:
                    avg_price = temp_positions[code]["cost_basis"] / temp_positions[code]["quantity"]
                    temp_positions[code]["quantity"] -= qty
                    temp_positions[code]["cost_basis"] -= qty * avg_price
                    if temp_positions[code]["quantity"] < 1e-9:
                        del temp_positions[code]

        self.capital = current_cash
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
        
        logging.info(f"已从交易历史恢复账户(完整回放)：现金{self.capital:.2f}，持仓标的{len(self.positions)}")

        # --- Equity anchor (anti-virtual-cash) ---
        # Force recovered cash/positions to align with corrected equity of previous trading day.
        # NOTE: This can introduce divergence vs trades replay if corrected equity / holdings breakdown are inconsistent.
        # Guard it behind an env flag.
        if os.getenv("ENABLE_EQUITY_ANCHOR", "false").lower() == "true":
            try:
                # Prefer explicitly set trading date (set by daily_task), else fall back.
                _d = str(getattr(self, "as_of_date", "") or getattr(self, "snapshot_date", "") or getattr(self, "current_date", "") or getattr(self, "today", ""))
                if not _d:
                    raise ValueError("no date on executor (set executor.as_of_date = 'YYYY-MM-DD' before restore)")
                res = anchor_account_to_corrected_equity(
                    date_str=_d,
                    recovered_cash=float(self.capital),
                    positions=self.positions,
                )
                self.capital = float(res.cash)
                self.positions = res.positions
                logging.info(f"[account-anchor] {res.note}")
            except Exception as e:
                logging.warning(f"[account-anchor] skipped: {e}")
        else:
            logging.info("[account-anchor] disabled (set ENABLE_EQUITY_ANCHOR=true to enable)")

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        total_value = float(self.capital)
        for etf_code, pos in self.positions.items():
            px = float(current_prices.get(etf_code, 0))
            total_value += float(pos.get("quantity", 0)) * (px if px > 0 else 0)
        return total_value
