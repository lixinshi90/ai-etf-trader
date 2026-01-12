# -*- coding: utf-8 -*-
from __future__ import annotations
"""
主任务调度：
- 每日收盘后执行：拉取数据 -> 风控检查 -> 获取AI决策(限流/缓存/重试) -> 规则信号 -> 合议 -> 执行交易 -> 打印账户总资产
- 启动时先立即执行一次 daily_task()
运行方式（确保在项目根目录）：
    python -m src.main
支持 .env 配置：
- CORE_ETF_LIST / OBSERVE_ETF_LIST / ETF_LIST
- SCHEDULE_TIME=17:00
- DAILY_AI_CALLS_LIMIT=3
- ENABLE_ENSEMBLE=true/false（默认 false）
- ENSEMBLE_MODE=CONSENSUS（目前仅实现一致同意：AI 与 规则同向才下单，否则 hold）

注意：
- 本文件为 2025-12-12 版本回滚（由 12_12_main.py 恢复），用于修复之前误覆盖导致的逻辑缺失。
- 日终快照写入前已接入 src.equity_guard.guard_daily_equity_write（B1：prev_cash+prev_holdings 基准）。
"""

import logging
import os
import sqlite3
import time as tm
from datetime import datetime
from typing import Optional

import pandas as pd
import schedule
from dotenv import load_dotenv

from src.ai_decision import get_ai_decision
from src.data_fetcher import fetch_etf_data, save_to_db
from src.trade_executor import TradeExecutor


# ---------------- Config helpers ----------------

def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def _etf_db_path() -> str:
    return os.path.join(_project_root(), "data", "etf_data.db")


def _decisions_dir() -> str:
    return os.path.join(_project_root(), "decisions")


def _parse_etf_list(env_val: str | None, default: list[str]) -> list[str]:
    if not env_val:
        return default
    items = [x.strip() for x in str(env_val).split(",") if x.strip()]
    return items or default


# ---------------- Pool filter (inline, keep compatibility) ----------------

def filter_etf_pool(etf_list: list[str]) -> list[str]:
    """根据流动性（日均成交额）和上市时间过滤ETF标的池（与 12_12_main.py 一致）。"""
    logger = logging.getLogger("main")
    try:
        filter_enabled = os.getenv("FILTER_ENABLED", "true").lower() == "true"
        if not filter_enabled:
            logger.info("标的池过滤未启用。")
            return etf_list

        min_avg_turnover = float(os.getenv("MIN_AVG_TURNOVER", "10000000"))  # 默认1000万
        min_listing_months = int(os.getenv("MIN_LISTING_MONTHS", "6"))
        turnover_lookback_days = 20
    except Exception as e:
        logger.warning(f"解析过滤参数失败: {e}，跳过过滤。")
        return etf_list

    logger.info(f"开始过滤标的池... 最小成交额: {min_avg_turnover/10000:.0f}万, 最短上市: {min_listing_months}月")

    try:
        import akshare as ak
        etf_info_df = ak.fund_etf_fund_info_em()
    except Exception as e:
        logger.warning(f"无法从akshare获取ETF基本信息: {e}，跳过过滤。")
        return etf_list

    filtered_list: list[str] = []
    for code in etf_list:
        try:
            info = etf_info_df[etf_info_df['基金代码'] == code]
            if info.empty:
                continue

            listing_date_str = info.iloc[0]['上市日期']
            listing_date = pd.to_datetime(listing_date_str)
            months_since_listing = (datetime.now() - listing_date).days / 30.44
            if months_since_listing < min_listing_months:
                logger.info(f"{code}: 上市时间（{months_since_listing:.1f}月）不足 {min_listing_months}月，已过滤。")
                continue

            hist_df = fetch_etf_data(code, days=turnover_lookback_days + 5)
            if hist_df.empty or len(hist_df) < turnover_lookback_days:
                logger.info(f"{code}: 历史数据不足，无法计算流动性，已过滤。")
                continue

            turnover_col = next((c for c in ["成交额", "turnover"] if c in hist_df.columns), None)
            if not turnover_col:
                filtered_list.append(code)
                continue

            avg_turnover = float(hist_df[turnover_col].tail(turnover_lookback_days).mean())
            if avg_turnover < min_avg_turnover:
                logger.info(f"{code}: 最近{turnover_lookback_days}日均成交额({avg_turnover/10000:.0f}万)过低，已过滤。")
                continue

            filtered_list.append(code)
        except Exception as e:
            logger.warning(f"过滤 {code} 时出错: {e}，默认保留。")
            if code not in filtered_list:
                filtered_list.append(code)

    logger.info(f"标的池过滤完成，剩余 {len(filtered_list)}/{len(etf_list)} 个标的: {','.join(filtered_list)}")
    return filtered_list


# ---------------- Prices helpers ----------------

def _read_latest_price_row(etf_code: str) -> tuple[str | None, float | None]:
    """Return (latest_date_str, latest_close) from etf DB for the given code.

    If latest close is missing/<=0, fall back to the most recent previous trading day's close (>0).
    """
    db_file = _etf_db_path()
    if not os.path.exists(db_file):
        return None, None

    def _read_last_n(limit: int) -> pd.DataFrame:
        conn = sqlite3.connect(db_file)
        try:
            try:
                return pd.read_sql_query(f"SELECT * FROM etf_{etf_code} ORDER BY 日期 DESC LIMIT {int(limit)}", conn)
            except Exception:
                return pd.read_sql_query(f"SELECT * FROM etf_{etf_code} ORDER BY date DESC LIMIT {int(limit)}", conn)
        except Exception:
            return pd.DataFrame()
        finally:
            conn.close()

    df = _read_last_n(60)
    if df.empty:
        return None, None

    # identify date/close columns
    date_col = None
    for c in ("日期", "date", "Date"):
        if c in df.columns:
            date_col = c
            break
    close_col = None
    for c in ("收盘", "收盘价", "close", "Close"):
        if c in df.columns:
            close_col = c
            break

    if not date_col or not close_col:
        return None, None

    # first row is latest (DESC)
    try:
        latest_date_str = str(df.iloc[0][date_col])
    except Exception:
        latest_date_str = None
    try:
        latest_close = float(df.iloc[0][close_col])
    except Exception:
        latest_close = None

    # Normal case
    if latest_date_str and latest_close is not None and latest_close > 0:
        return latest_date_str, latest_close

    # Fallback: find most recent prior row with close>0
    if latest_date_str:
        for i in range(1, len(df)):
            try:
                dstr = str(df.iloc[i][date_col])
                cval = float(df.iloc[i][close_col])
            except Exception:
                continue
            if not dstr or dstr >= latest_date_str:
                continue
            if cval > 0:
                logging.getLogger("main").warning(
                    f"[price-fallback] {etf_code} latest close invalid ({latest_close}), using prev close {dstr}={cval}"
                )
                return latest_date_str, cval

    # If we cannot find a previous valid close, return what we have
    return latest_date_str, latest_close


def _read_latest_price(etf_code: str) -> float | None:
    _, px = _read_latest_price_row(etf_code)
    return px


def _latest_market_date(all_etfs: list[str]) -> datetime.date | None:
    """Infer the latest market date from etf DB across all_etfs."""
    latest: datetime.date | None = None
    for etf in all_etfs:
        dstr, _ = _read_latest_price_row(etf)
        if not dstr:
            continue
        try:
            d = pd.to_datetime(dstr).date()
        except Exception:
            continue
        if latest is None or d > latest:
            latest = d
    return latest


# ---------------- Rule-based Signals + Ensemble ----------------
# 说明：我们使用本文件内的实现（来自 2025-12-12 版本回滚），避免引用以数字开头的模块名。


def get_rule_decision(df: pd.DataFrame, params: dict, etf_code: str | None = None) -> dict:
    df = df.copy()
    mode = str(params.get("mode", "MA_CROSS")).upper()
    signals: list[dict] = []

    def _find_col(*args):
        for c in args:
            if c in df.columns:
                return c
        return None

    close_col = _find_col("收盘", "收盘价", "close", "Close")
    high_col = _find_col("最高", "最高价", "high", "High")
    low_col = _find_col("最低", "最低价", "low", "Low")

    if not close_col:
        return {"decision": "hold", "reasoning": "规则：无收盘价数据", "confidence": 0.5}

    close = df[close_col]
    latest_close = close.iloc[-1]

    def _ma_cross():
        if len(df) < 61:
            return None
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        if (ma20.iloc[-2] <= ma60.iloc[-2]) and (ma20.iloc[-1] > ma60.iloc[-1]) and (latest_close > ma20.iloc[-1]):
            return {"decision": "buy", "reasoning": "规则：MA20上穿MA60", "confidence": 0.6}
        if (ma20.iloc[-2] >= ma60.iloc[-2]) and (ma20.iloc[-1] < ma60.iloc[-1]) and (latest_close < ma20.iloc[-1]):
            return {"decision": "sell", "reasoning": "规则：MA20下穿MA60", "confidence": 0.6}
        return None

    def _breakout():
        if not high_col or not low_col:
            return None
        n = int(params.get("breakout_n", 20) or 20)
        if len(df) < n + 1:
            return None
        donchian_high = df[high_col].rolling(n).max().shift(1)
        if latest_close > donchian_high.iloc[-1]:
            return {"decision": "buy", "reasoning": f"规则：突破{n}日高点", "confidence": 0.65}
        return None

    def _mean_reversion():
        n = int(params.get("rsi_n", 2) or 2)
        if len(df) < n + 1:
            return None
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=n).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=n).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        if rsi.iloc[-1] < float(params.get("rsi_low", 10) or 10):
            return {"decision": "buy", "reasoning": f"规则：RSI({n})超卖", "confidence": 0.7}
        if rsi.iloc[-1] > float(params.get("rsi_high", 95) or 95):
            return {"decision": "sell", "reasoning": f"规则：RSI({n})超买", "confidence": 0.7}
        return None

    def _kdj_macd_signal():
        if not all(c in df.columns for c in ['k', 'd', 'j', 'dif', 'dea', 'macd']):
            return None
        kdj_low = float(params.get("kdj_low", 20) or 20)
        j_cross_up = (df['j'].iloc[-2] < kdj_low) and (df['j'].iloc[-1] > kdj_low)
        macd_cross_up = (df['dif'].iloc[-2] < df['dea'].iloc[-2]) and (df['dif'].iloc[-1] > df['dea'].iloc[-1])
        if j_cross_up and macd_cross_up:
            return {"decision": "buy", "reasoning": f"规则：KDJ探底(J>{kdj_low:.0f}) + MACD金叉", "confidence": 0.75}
        return None

    if mode == "MA_CROSS":
        s = _ma_cross()
        if s:
            signals.append(s)
    elif mode == "BREAKOUT":
        s = _breakout()
        if s:
            signals.append(s)
    elif mode == "MEAN_REVERSION":
        s = _mean_reversion()
        if s:
            signals.append(s)
    elif mode == "KDJ_MACD":
        s = _kdj_macd_signal()
        if s:
            signals.append(s)
    else:  # AGGRESSIVE
        for fn in (_breakout, _mean_reversion, _ma_cross, _kdj_macd_signal):
            s = fn()
            if s:
                signals.append(s)

    if not signals:
        return {"decision": "hold", "reasoning": "规则：无信号", "confidence": 0.5}

    signals.sort(key=lambda x: (x["decision"] != 'buy', x["decision"] != 'sell', -x.get("confidence", 0)))
    return signals[0]


def validate_decision(decision: dict, price: float) -> dict:
    out = dict(decision) if isinstance(decision, dict) else {"decision": "hold"}
    out.setdefault("decision", "hold")
    try:
        out["confidence"] = float(out.get("confidence", 0.5))
    except Exception:
        out["confidence"] = 0.5
    out.setdefault("reasoning", "")
    out.setdefault("stop_loss", None)
    out.setdefault("take_profit", None)
    return out


def ensemble_decision(ai_dec: dict, rule_dec: dict, mode: str = "CONSENSUS") -> dict:
    """Combine AI decision and rule decision.

    Modes:
    - CONSENSUS (legacy): AI 与规则同向才交易，否则 hold
    - AI_VETO (recommended): AI 主导，规则仅作为否决（提升交易频率）
        * buy: AI=buy 且 规则!=sell -> buy
        * sell: AI=sell 且 规则!=buy -> sell
        * 若规则明确反向（buy vs sell）则 hold
    """
    m = str(mode).upper()
    ai = (ai_dec or {}).get("decision", "hold")
    rl = (rule_dec or {}).get("decision", "hold")

    if m == "CONSENSUS":
        if ai == rl and ai in ("buy", "sell"):
            reason = f"合议一致：AI({ai_dec.get('confidence')}) {ai_dec.get('reasoning')} | 规则({rule_dec.get('confidence')}) {rule_dec.get('reasoning')}"
            conf = (float(ai_dec.get("confidence", 0.5)) + float(rule_dec.get("confidence", 0.5))) / 2.0
            merged = dict(ai_dec)
            merged.update({"reasoning": reason, "confidence": conf})
            return merged
        return {
            "decision": "hold",
            "confidence": 0.5,
            "reasoning": f"合议分歧：AI={ai}，规则={rl}，默认持有",
            "stop_loss": None,
            "take_profit": None,
        }

    # Default to AI_VETO for any other mode value
    # 规则强反向时否决（避免明显冲突）
    if (ai == "buy" and rl == "sell") or (ai == "sell" and rl == "buy"):
        return {
            "decision": "hold",
            "confidence": 0.5,
            "reasoning": f"规则否决：AI={ai}，规则={rl}（强反向），默认持有",
            "stop_loss": None,
            "take_profit": None,
        }

    if ai == "buy" and rl != "sell":
        merged = dict(ai_dec)
        merged["reasoning"] = f"AI主导买入：AI({ai_dec.get('confidence')}) {ai_dec.get('reasoning')} | 规则={rl}"
        return merged

    if ai == "sell" and rl != "buy":
        merged = dict(ai_dec)
        merged["reasoning"] = f"AI主导卖出：AI({ai_dec.get('confidence')}) {ai_dec.get('reasoning')} | 规则={rl}"
        return merged

    # AI=hold 或规则为 hold：默认返回 AI（更贴近“AI主导”）
    return ai_dec


# ---------------- Main daily task ----------------

def daily_task(executor: TradeExecutor, core_list: list[str], observe_list: list[str], daily_ai_limit: int, force_date: Optional[datetime.date] = None):
    # 直接复用 12_12_main 的 daily_task 逻辑，但替换“日终快照写入”段落
    # 为了保持最小风险，这里不做重构，直接 copy 12_12_main.py 中的实现并在写快照处接入 equity_guard。

    logger = logging.getLogger("main")
    logger.info("=== %s 每日任务开始 ===", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # Expose the effective trading date on the executor so recovery/anchoring logic can use it.
    # If running after-hours (e.g., after midnight), we still want to write snapshots for the
    # latest market date (usually yesterday) rather than "today".
    snapshot_date = force_date if force_date else (_latest_market_date(sorted(list(set(core_list + observe_list)))) or datetime.now().date())
    executor.as_of_date = snapshot_date.strftime("%Y-%m-%d")

    # --- 1. 数据准备 (合并所有列表以统一拉取) ---
    all_etfs = sorted(list(set(core_list + observe_list)))
    for etf in all_etfs:
        try:
            df = fetch_etf_data(etf, days=700, end_date=force_date.strftime("%Y%m%d") if force_date else None)
            save_to_db(df, etf, db_path=_etf_db_path())
            logger.info(f"已更新 {etf} 数据{' (截至 ' + force_date.strftime('%Y-%m-%d') + ')' if force_date else ''}")
        except Exception as e:
            logger.warning(f"更新 {etf} 失败: {e}")

    current_prices: dict[str, float] = {}
    latest_dfs: dict[str, pd.DataFrame] = {}
    db_file = _etf_db_path()
    for etf in all_etfs:
        price = _read_latest_price(etf)
        if price is not None:
            current_prices[etf] = price

        if os.path.exists(db_file):
            conn = sqlite3.connect(db_file)
            try:
                df = pd.read_sql_query(f"SELECT * FROM etf_{etf} ORDER BY 日期 ASC", conn)
            except Exception:
                df = pd.DataFrame()
            finally:
                conn.close()
            if not df.empty:
                latest_dfs[etf] = df.tail(200)
                if etf not in current_prices:
                    px = df.iloc[-1].get('收盘', df.iloc[-1].get('close'))
                    if pd.notna(px):
                        current_prices[etf] = float(px)

    # 风控（自动止损/止盈等）
    executor.auto_risk_sell(current_prices, latest_dfs)

    # --- 2. 决策生成 (分层处理) ---
    decisions_to_execute = {}
    core_buy_signal_found = False
    ai_calls_this_run = 0

    def _process_etf(etf: str):
        nonlocal ai_calls_this_run
        df = latest_dfs.get(etf)
        if df is None or df.empty:
            logger.warning("%s 无足够数据，跳过决策", etf)
            return None

        strategy_mode = os.getenv("STRATEGY_MODE", "AGGRESSIVE")
        rule_params = {
            "mode": strategy_mode,
            "breakout_n": int(os.getenv("BREAKOUT_N", "20")),
            "rsi_n": int(os.getenv("RSI_N", "2")),
            "rsi_low": int(os.getenv("RSI_LOW", "10")),
            "rsi_high": int(os.getenv("RSI_HIGH", "95")),
            "kdj_low": int(os.getenv("KDJ_LOW", "20")),
        }
        rd = get_rule_decision(df, rule_params, etf_code=etf)

        # AI 调用优化：默认只对“规则有信号”的标的调用 AI，避免对大量 hold 标的浪费配额。
        # 若你仍想全量调用，可设置 AI_CALL_ONLY_ON_RULE_SIGNAL=false
        ai_only_on_signal = os.getenv("AI_CALL_ONLY_ON_RULE_SIGNAL", "true").lower() == "true"
        rule_is_signal = str((rd or {}).get("decision", "hold")).lower() in ("buy", "sell")

        ai_dec = {"decision": "hold", "confidence": 0.5, "reasoning": "AI跳过/限流或异常"}
        try:
            if (not ai_only_on_signal) or rule_is_signal:
                if ai_calls_this_run < daily_ai_limit:
                    ai_dec = get_ai_decision(etf, df, force_date=force_date)
                    ai_calls_this_run += 1
                else:
                    logger.info("已达当日AI调用上限(%s)，%s 使用默认持有策略", daily_ai_limit, etf)
            else:
                ai_dec = {"decision": "hold", "confidence": 0.5, "reasoning": "规则无信号，跳过AI调用"}
        except Exception as e:
            logger.warning("AI决策失败，%s 使用规则策略：%s", etf, e)

        # 合议（最终决策）
        mode = os.getenv("ENSEMBLE_MODE", "CONSENSUS")
        final_decision = ensemble_decision(ai_dec, rd, mode)

        # 关键诊断日志：把 AI/规则/合议结果一次性打出来，方便定位“为什么没交易”
        try:
            logger.info(
                "[decision] %s mode=%s | ai=%s(%.2f) | rule=%s(%.2f) | final=%s(%.2f)",
                etf,
                str(mode).upper(),
                (ai_dec or {}).get("decision"),
                float((ai_dec or {}).get("confidence", 0.5) or 0.5),
                (rd or {}).get("decision"),
                float((rd or {}).get("confidence", 0.5) or 0.5),
                (final_decision or {}).get("decision"),
                float((final_decision or {}).get("confidence", 0.5) or 0.5),
            )
            logger.info("[decision] %s ai_reason=%s", etf, (ai_dec or {}).get("reasoning", ""))
            logger.info("[decision] %s rule_reason=%s", etf, (rd or {}).get("reasoning", ""))
            logger.info("[decision] %s final_reason=%s", etf, (final_decision or {}).get("reasoning", ""))
        except Exception:
            logger.exception("[decision] %s decision logging failed", etf)

        px_for_val = current_prices.get(etf, 0.0)
        final_decision = validate_decision(final_decision, px_for_val)
        return etf, final_decision

    logger.info(f"--- 开始处理核心池 ({len(core_list)}个) ---")
    for etf in core_list:
        result = _process_etf(etf)
        if result:
            decisions_to_execute[result[0]] = result[1]
            if result[1].get('decision') == 'buy':
                core_buy_signal_found = True

    if not core_buy_signal_found and observe_list:
        logger.info(f"--- 核心池无买入信号，开始处理观察池 ({len(observe_list)}个) ---")
        for etf in observe_list:
            result = _process_etf(etf)
            if result:
                decisions_to_execute[result[0]] = result[1]
    elif observe_list:
        logger.info("--- 核心池已产生买入信号，跳过观察池。 ---")

    logger.info("--- 开始执行所有决策 ---")
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if dry_run:
        logger.warning("[DRY_RUN] mode enabled, skipping all trade executions.")

    for etf, decision in decisions_to_execute.items():
        if etf in current_prices:
            if not dry_run:
                executor.execute_trade(etf, decision, current_prices[etf], current_prices)
            else:
                action = str(decision.get("decision", "hold")).lower()
                if action in ("buy", "sell"):
                    logger.info(f"[DRY_RUN] SKIPPED: {action.upper()} {etf} @ {current_prices.get(etf)}")

    # --- 4. 写入日终快照（带明细日志 + 源头加固 B1） ---
    holdings_value = 0.0
    missing_px: list[str] = []
    try:
        if getattr(executor, 'positions', None):
            for code, pos in executor.positions.items():
                qty = float(pos.get('quantity', 0) or 0)
                px = float(current_prices.get(code, 0) or 0)
                if px <= 0:
                    missing_px.append(code)
                val = qty * (px if px > 0 else 0)
                holdings_value += val
                logger.info(f"[equity-breakdown] {code} qty={qty:.4f} px={px:.4f} val={val:.2f}")
        logger.info(f"[equity-breakdown] cash={executor.capital:.2f} holdings={holdings_value:.2f} missing_px={missing_px}")
    except Exception:
        logger.exception("[equity-breakdown] 计算失败")

    # Use latest market date (from DB) as snapshot date to avoid after-midnight date shift.
    snapshot_date = force_date if force_date else (_latest_market_date(all_etfs) or datetime.now().date())
    snapshot_date_str = snapshot_date.strftime("%Y-%m-%d")

    final_equity = executor.get_portfolio_value(current_prices)

    # Persist holdings breakdown for next-day recovery anchoring (uses final snapshot_date_str).
    try:
        out_dir = os.path.join(_project_root(), "out")
        _ensure_dir(out_dir)
        hb_path = os.path.join(out_dir, f"holdings_breakdown_{snapshot_date_str}.csv")
        import csv
        with open(hb_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["code", "qty_asof", "close_asof", "value", "flags"])
            if getattr(executor, 'positions', None):
                for code, pos in executor.positions.items():
                    qty = float(pos.get('quantity', 0) or 0)
                    px = float(current_prices.get(code, 0) or 0)
                    w.writerow([code, qty, px, qty * (px if px > 0 else 0), "missing_px" if px <= 0 else ""])
        logger.info(f"[holdings-breakdown] wrote: {hb_path}")
    except Exception as e:
        logger.warning(f"[holdings-breakdown] export failed: {e}")

    try:
        from src.equity_guard import guard_daily_equity_write

        etf_db_path = os.path.join(_project_root(), 'data', 'etf_data.db')

        guard = guard_daily_equity_write(
            db_path=executor.db_path,
            snapshot_date=snapshot_date_str,
            final_equity=float(final_equity),
            missing_px=missing_px,
            max_daily_change_pct=float(os.getenv("EQUITY_GUARD_MAX_DAILY_CHANGE_PCT", "10")),  # 过渡期建议 8~10，稳定后可改回 5
            allow_overwrite=False,
            etf_db_path=etf_db_path,
            initial_capital=float(os.getenv('INITIAL_CAPITAL', '100000')),
            current_cash=float(executor.capital),
        )

        if not guard.ok:
            logger.error(f"[equity-guard] 拒绝写入日终快照 {snapshot_date_str}: {final_equity:.2f} | reason={guard.reason}")
            if guard.prev_date and guard.prev_equity is not None and guard.pct_change is not None:
                logger.error(f"[equity-guard] prev={guard.prev_date} base={guard.prev_equity:.2f} change={guard.pct_change:.2f}%")
            # 关键：拒绝写入时直接退出，避免后续导出/因子污染
            raise SystemExit(2)
        else:
            if guard.pct_change is not None:
                logger.info(f"[equity-guard] 通过: {snapshot_date_str} equity={final_equity:.2f}, change={guard.pct_change:.2f}%")

    except SystemExit:
        raise
    except Exception as e:
        logger.exception(f"[equity-guard] 校验异常（为安全起见拒绝写入）: {e}")
        raise SystemExit(2)

    # --- 4.5 日终一致性校验（replay guard）：用 trades 回放状态与运行态对账，避免污染后续 daily_equity ---
    try:
        guard_enabled = os.getenv("EQUITY_REPLAY_GUARD", "true").lower() == "true"
        max_abs_diff = float(os.getenv("EQUITY_REPLAY_MAX_ABS_DIFF", "10"))  # 元
        qty_tol = float(os.getenv("EQUITY_REPLAY_QTY_TOL", "1e-6"))

        if guard_enabled:
            import pandas as _pd

            # 1) 从 trades 表回放到 snapshot_date_str 当日结束（<= 23:59:59）
            conn_g = sqlite3.connect(executor.db_path)
            try:
                tdf = _pd.read_sql_query(
                    "SELECT date, etf_code, action, price, quantity, value, capital_after, reasoning FROM trades ORDER BY datetime(date)",
                    conn_g,
                )
            finally:
                conn_g.close()

            tdf["date"] = _pd.to_datetime(tdf["date"], errors="coerce")
            tdf = tdf.dropna(subset=["date"]).copy()
            cutoff = _pd.to_datetime(snapshot_date_str) + _pd.Timedelta(days=1) - _pd.Timedelta(seconds=1)
            tdf = tdf[tdf["date"] <= cutoff]

            # 推断回放起始现金：用第一条交易反推（避免 INITIAL_CAPITAL 与真实起点不一致）
            default_ic = float(os.getenv('INITIAL_CAPITAL', '100000'))
            replay_cash = default_ic
            try:
                if not tdf.empty:
                    first = tdf.iloc[0]
                    first_act = str(first.get('action') or '').lower()
                    first_gross = float(first.get('value') or 0.0)
                    first_cap_after = float(first.get('capital_after') or 0.0) if 'capital_after' in tdf.columns else None
                    first_reason = str(first.get('reasoning') or '')

                    # 从 reasoning 解析成本
                    first_cost = 0.0
                    try:
                        m0 = __import__('re').search(r"成本:\s*([0-9]+(?:\.[0-9]+)?)", first_reason)
                        if m0:
                            first_cost = float(m0.group(1))
                    except Exception:
                        first_cost = 0.0

                    # 如果 trades 表里有 capital_after（trade_history.db 默认有），用它来反推初始现金
                    if first_cap_after is not None and first_cap_after > 0 and first_gross > 0 and first_act in ('buy','sell'):
                        if first_act == 'buy':
                            replay_cash = float(first_cap_after) + float(first_gross) + float(first_cost)
                        else:
                            # sell: cap_after = cash_before + (gross - cost) => cash_before = cap_after - gross + cost
                            replay_cash = float(first_cap_after) - float(first_gross) + float(first_cost)
                        logger.info(f"[equity-replay-guard] inferred initial cash={replay_cash:.2f} (default INITIAL_CAPITAL={default_ic:.2f})")
            except Exception as _e0:
                logger.warning(f"[equity-replay-guard] failed to infer initial cash, fallback to INITIAL_CAPITAL={default_ic:.2f}: {_e0}")

            replay_pos: dict[str, float] = {}

            for _, r in tdf.iterrows():
                code = str(r.get("etf_code") or "").strip()
                act = str(r.get("action") or "").lower()
                qty = float(r.get("quantity") or 0.0)
                gross = float(r.get("value") or 0.0)  # trades.value 通常为成交额(gross)
                reason = str(r.get("reasoning") or "")

                # 尽力从 reasoning 中解析成本（execute_trade 会写入 "成本: xx.xx"）
                cost = 0.0
                try:
                    m = __import__('re').search(r"成本:\s*([0-9]+(?:\.[0-9]+)?)", reason)
                    if m:
                        cost = float(m.group(1))
                except Exception:
                    cost = 0.0

                if not code:
                    continue

                if act == "buy":
                    # buy 现金流：-(gross + cost)
                    replay_cash -= (gross + cost)
                    replay_pos[code] = replay_pos.get(code, 0.0) + qty
                elif act == "sell":
                    # sell 现金流：+(gross - cost)
                    replay_cash += (gross - cost)
                    replay_pos[code] = replay_pos.get(code, 0.0) - qty

            replay_pos = {k: v for k, v in replay_pos.items() if abs(v) > qty_tol}

            # 2) 运行态 positions/cash
            run_cash = float(executor.capital)
            run_pos = {k: float(v.get('quantity', 0) or 0) for k, v in (executor.positions or {}).items()}
            run_pos = {k: v for k, v in run_pos.items() if abs(v) > qty_tol}

            # 3) 对比 qty
            codes = sorted(set(replay_pos) | set(run_pos))
            qty_diffs = []
            for c in codes:
                rq = float(replay_pos.get(c, 0.0))
                uq = float(run_pos.get(c, 0.0))
                qd = uq - rq
                if abs(qd) > qty_tol:
                    px = float(current_prices.get(c, 0.0) or 0.0)
                    qty_diffs.append((c, uq, rq, qd, px, qd * px))

            # 4) 对比总资产（用当日 current_prices 估值）
            def _value(pos: dict[str, float]) -> float:
                s = 0.0
                for c, q in pos.items():
                    px = float(current_prices.get(c, 0.0) or 0.0)
                    s += float(q) * (px if px > 0 else 0.0)
                return s

            replay_total = replay_cash + _value(replay_pos)
            run_total = run_cash + _value(run_pos)
            diff = run_total - replay_total

            if abs(diff) > max_abs_diff or qty_diffs:
                logger.error(
                    "[equity-replay-guard] FAILED %s | run_total=%.4f replay_total=%.4f diff=%.4f (threshold=%.2f)",
                    snapshot_date_str,
                    run_total,
                    replay_total,
                    diff,
                    max_abs_diff,
                )
                logger.error("[equity-replay-guard] run_cash=%.4f replay_cash=%.4f", run_cash, replay_cash)

                # 输出差异明细到 CSV，便于审计与报告附录
                try:
                    out_dir = os.path.join(_project_root(), "out")
                    _ensure_dir(out_dir)
                    fp = os.path.join(out_dir, f"equity_replay_guard_failed_{snapshot_date_str}.csv")

                    # 汇总表头：现金与总资产差异 + 每个标的 qty/value 差异
                    rows = []
                    for c in codes:
                        uq = float(run_pos.get(c, 0.0))
                        rq = float(replay_pos.get(c, 0.0))
                        qd = uq - rq
                        px = float(current_prices.get(c, 0.0) or 0.0)
                        rows.append({
                            "code": c,
                            "run_qty": uq,
                            "replay_qty": rq,
                            "qty_diff": qd,
                            "px": px,
                            "value_diff": qd * px,
                        })

                    import pandas as __pd
                    df_out = __pd.DataFrame(rows)
                    df_out = df_out.sort_values(by="value_diff", key=lambda s: s.abs(), ascending=False)
                    # 在 CSV 顶部写入一行 summary（用额外列承载）
                    summary = {
                        "code": "__SUMMARY__",
                        "snapshot_date": snapshot_date_str,
                        "db_path": str(getattr(executor, 'db_path', '')),
                        "threshold_abs_diff": max_abs_diff,
                        "qty_tol": qty_tol,
                        "missing_px": ";".join(missing_px) if isinstance(missing_px, list) else str(missing_px),
                        "market_date_used": snapshot_date_str,
                        "run_total": run_total,
                        "replay_total": replay_total,
                        "total_diff": diff,
                        "run_cash": run_cash,
                        "replay_cash": replay_cash,
                    }

                    # 让 summary 与明细共享同一列集合（缺失列填空）
                    df_summary = __pd.DataFrame([summary])
                    df_out2 = df_out.copy()
                    df_out2.insert(0, "snapshot_date", snapshot_date_str)
                    df_out2.insert(1, "db_path", str(getattr(executor, 'db_path', '')))
                    df_out2.insert(2, "threshold_abs_diff", max_abs_diff)
                    df_out2.insert(3, "qty_tol", qty_tol)
                    df_out2.insert(4, "missing_px", ";".join(missing_px) if isinstance(missing_px, list) else str(missing_px))
                    df_out2.insert(5, "market_date_used", snapshot_date_str)

                    df_final = __pd.concat([df_summary, df_out2], ignore_index=True)
                    df_final.to_csv(fp, index=False, encoding="utf-8-sig")

                    # 额外输出 Top10（更便于截图/附录）
                    fp_top = os.path.join(out_dir, f"equity_replay_guard_failed_{snapshot_date_str}_top10.csv")
                    df_out2.head(10).to_csv(fp_top, index=False, encoding="utf-8-sig")

                    logger.error(f"[equity-replay-guard] wrote diff report: {fp}")
                    logger.error(f"[equity-replay-guard] wrote top10 report: {fp_top}")
                except Exception as e2:
                    logger.error(f"[equity-replay-guard] failed to write diff report: {e2}")

                if qty_diffs:
                    qty_diffs.sort(key=lambda x: abs(x[5]), reverse=True)
                    logger.error("[equity-replay-guard] top position diffs (code run_qty replay_qty qty_diff px value_diff):")
                    for c, uq, rq, qd, px, vd in qty_diffs[:10]:
                        logger.error("  - %s %.6f %.6f %.6f px=%.4f value_diff=%.4f", c, uq, rq, qd, px, vd)

                # 拒绝写入，防止污染
                raise SystemExit(2)
            else:
                logger.info(
                    "[equity-replay-guard] OK %s | run_total=%.4f replay_total=%.4f diff=%.4f",
                    snapshot_date_str,
                    run_total,
                    replay_total,
                    diff,
                )
    except SystemExit:
        raise
    except Exception as e:
        logger.exception(f"[equity-replay-guard] exception: {e}")
        raise SystemExit(2)

    try:
        conn = sqlite3.connect(executor.db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")
        conn.execute(
            "INSERT INTO daily_equity(date, equity) VALUES(?,?)",
            (snapshot_date_str, float(final_equity)),
        )
        conn.commit()
        logger.info(f"已写入日终快照 {snapshot_date_str}: {float(final_equity):.2f}")
    except Exception as e:
        logger.error(f"写入日终快照失败: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    logger.info("=== 每日任务结束 ===\n")


def _setup_logging():
    """Initialize console and file logging consistent with daily_once."""
    logs_dir = os.path.join(_project_root(), "logs")
    _ensure_dir(logs_dir)
    log_file = os.path.join(logs_dir, "daily.log")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    logger.handlers = []
    logger.addHandler(ch)
    logger.addHandler(fh)


if __name__ == "__main__":
    load_dotenv(override=True)
    _setup_logging()

    default_etfs = ["510050", "159915", "510300"]
    core_env = os.getenv("CORE_ETF_LIST", os.getenv("ETF_LIST"))
    core_etfs = _parse_etf_list(core_env, default_etfs)
    observe_etfs = _parse_etf_list(os.getenv("OBSERVE_ETF_LIST"), [])

    core_etfs = filter_etf_pool(core_etfs)
    observe_etfs = filter_etf_pool(observe_etfs)

    try:
        daily_ai_limit = int(os.getenv("DAILY_AI_CALLS_LIMIT", str(len(core_etfs) + len(observe_etfs))))
    except Exception:
        daily_ai_limit = len(core_etfs) + len(observe_etfs)

    try:
        init_cap = float(os.getenv("INITIAL_CAPITAL", "100000"))
    except Exception:
        init_cap = 100000.0

    executor = TradeExecutor(initial_capital=init_cap)
    daily_task(executor, core_etfs, observe_etfs, daily_ai_limit)

    schedule_time = os.getenv("SCHEDULE_TIME", "")
    if schedule_time:
        schedule.every().day.at(schedule_time).do(daily_task, executor, core_etfs, observe_etfs, daily_ai_limit)
        while True:
            schedule.run_pending()
            tm.sleep(1)
