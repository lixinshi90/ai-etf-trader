# -*- coding: utf-8 -*-
from __future__ import annotations
"""
一次性执行每日任务：拉数 -> 风控 -> AI决策 -> 交易 -> 日志 -> 退出。
用于 Windows 任务计划程序或任意定时器按天调度。
用法：
    conda run -n ai-etf-trader python -m src.daily_once
"""
import os
import sqlite3
import pandas as pd
import yaml
from datetime import datetime
from dotenv import load_dotenv

from src.main import (
    daily_task,
    _parse_etf_list,
    _project_root,
    _ensure_dir,
)
from src.trade_executor import TradeExecutor
import logging

# optional qlib adapter + factor run
try:
    from src.qlib_adapter import main as qlib_export_main
except Exception:
    qlib_export_main = None
try:
    from src.qlib_run import run as qlib_factor_run
except Exception:
    qlib_factor_run = None


def _setup_logging_once():
    # 与 main 中保持一致的日志落盘
    logs_dir = os.path.join(_project_root(), "logs")
    _ensure_dir(logs_dir)
    log_file = os.path.join(logs_dir, "daily.log")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 控制台
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    # 文件
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    logger.handlers = []
    logger.addHandler(ch)
    logger.addHandler(fh)


def _log_risk_config():
    logger = logging.getLogger("once")
    try:
        cfg_path = os.path.join(_project_root(), "config.yaml")
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        st = cfg.get('strategy', {}) if isinstance(cfg, dict) else {}
        cs = cfg.get('costs', {}) if isinstance(cfg, dict) else {}
        logger.info("[risk] initial_capital=%.2f, max_position_pct=%.2f%%", float(st.get('initial_capital', 100000.0)), float(st.get('max_position_pct', 0.2))*100)
        logger.info("[risk] costs: buy_slippage=%.4f, buy_commission=%.4f, sell_slippage=%.4f, sell_commission=%.4f, sell_tax=%.4f",
                    float(cs.get('buy_slippage', 0.001)), float(cs.get('buy_commission', 0.0005)), float(cs.get('sell_slippage', 0.001)), float(cs.get('sell_commission', 0.0005)), float(cs.get('sell_tax', 0.001)))
    except Exception as e:
        logger.warning("[risk] 读取风控配置失败：%s", e)


def _export_compliant_csv_from_db():
    logger = logging.getLogger("once")
    try:
        db_path = os.path.join(_project_root(), "data", "trade_history.db")
        out_dir = os.path.join(_project_root(), "out")
        os.makedirs(out_dir, exist_ok=True)
        if not os.path.exists(db_path):
            logger.info("[export] 无 DB，跳过导出")
            return
        conn = sqlite3.connect(db_path)
        try:
            # trades (robust to schema diffs)
            tdf = pd.read_sql_query("SELECT * FROM trades ORDER BY datetime(date)", conn)
            expected_cols = [
                'id','date','etf_code','action','price','quantity','value','capital_after','reasoning',
                'prev_cash','trade_pct','constraint_triggered','trade_cost'
            ]
            cols = [c for c in expected_cols if c in tdf.columns]
            if cols:
                tdf = tdf[cols]
            tdf.to_csv(os.path.join(out_dir, 'resimulated_trades_fully_compliant.csv'), index=False, encoding='utf-8-sig')
            # daily_equity -> equity csv
            edf = pd.read_sql_query("SELECT date, equity FROM daily_equity ORDER BY date", conn)
            edf.to_csv(os.path.join(out_dir, 'resimulated_daily_equity.csv'), index=False, encoding='utf-8-sig')
            # performance (simple)
            pdf = edf.copy()
            pdf = pdf.rename(columns={"equity":"total_assets"})
            pdf['daily_return_pct'] = pdf['total_assets'].pct_change().fillna(0.0) * 100.0
            pdf.to_csv(os.path.join(out_dir, 'resimulated_daily_performance.csv'), index=False, encoding='utf-8-sig')
            logger.info("[export] 已生成合规CSV: trades/equity/performance")
        finally:
            conn.close()
    except Exception as e:
        logger.warning("[export] 合规CSV导出失败：%s", e)


def main():
    load_dotenv(override=True)
    _setup_logging_once()

    logger = logging.getLogger("once")
    logger.info("[daily_once] 启动一次性每日任务...")
    _log_risk_config()

    default_etfs = ["510050", "159915", "510300"]
    etf_list = _parse_etf_list(os.getenv("ETF_LIST"), default_etfs)

    # --- Trading-day guard (authoritative): skip on holidays/weekends ---
    # Uses akshare official calendar. Override with FORCE_RUN=true.
    try:
        if os.getenv("FORCE_RUN", "false").lower() != "true":
            import akshare as ak
            import pandas as pd

            logger.info("[daily_once] 正在获取A股交易日历...")
            trade_cal = ak.tool_trade_date_hist_sina()
            trade_dates = set(pd.to_datetime(trade_cal['trade_date']).dt.date)
            today = datetime.now().date()

            if today not in trade_dates:
                logger.info(f"[daily_once] 今日 {today} 非A股交易日，跳过每日任务。")
                return
            logger.info(f"[daily_once] 今日 {today} 是交易日，继续执行。")
    except Exception as e:
        # If calendar fetch fails, fall back to old logic for resilience
        logger.warning(f"[daily_once] 获取交易日历失败（{e}），回退到基于本地数据的推断逻辑。")
        try:
            if os.getenv("FORCE_RUN", "false").lower() != "true":
                from src.main import _latest_market_date
                latest_mkt = _latest_market_date(etf_list)
                today = datetime.now().date()
                if latest_mkt is not None and latest_mkt < today:
                    logger.info(f"[daily_once] [fallback] 今日 {today} 无新行情（最新交易日={latest_mkt}），跳过每日任务。")
                    return
        except Exception as e2:
            logger.error(f"[daily_once] [fallback] 交易日判断失败（将继续运行）：{e2}")

    try:
        daily_ai_limit = int(os.getenv("DAILY_AI_CALLS_LIMIT", str(len(etf_list))))
    except Exception:
        daily_ai_limit = len(etf_list)

    executor = TradeExecutor(initial_capital=100000.0)
    # Provide an explicit trading date for recovery/anchoring logic
    executor.as_of_date = datetime.now().strftime("%Y-%m-%d")

    # 恢复上一次交易后的账户与持仓，保证从前一日状态继续
    try:
        executor.restore_state_from_db()
    except Exception:
        pass

    # 可选一次性对齐：若启用 ENABLE_COMPLIANT_ALIGN=true，则用合规CSV回填DB，防止历史“虚高”污染
    if os.getenv("ENABLE_COMPLIANT_ALIGN", "false").lower() == "true":
        try:
            csv_path = os.path.join(_project_root(), "out", "resimulated_daily_equity.csv")
            trades_csv = os.path.join(_project_root(), "out", "resimulated_trades_fully_compliant.csv")
            if os.path.exists(csv_path) and os.path.exists(trades_csv):
                def _latest_price(code: str) -> float:
                    db = os.path.join(_project_root(), "data", "etf_data.db")
                    if not os.path.exists(db):
                        return 0.0
                    conn2 = sqlite3.connect(db)
                    try:
                        try:
                            dfp = pd.read_sql_query(f"SELECT * FROM etf_{code} ORDER BY 日期 DESC LIMIT 1", conn2)
                        except Exception:
                            dfp = pd.read_sql_query(f"SELECT * FROM etf_{code} ORDER BY date DESC LIMIT 1", conn2)
                        if not dfp.empty:
                            for col in ("收盘", "收盘价", "close", "Close"):
                                if col in dfp.columns:
                                    try:
                                        return float(dfp.iloc[0][col])
                                    except Exception:
                                        continue
                    except Exception:
                        return 0.0
                    finally:
                        conn2.close()
                    return 0.0

                equity_csv = pd.read_csv(csv_path)
                if not equity_csv.empty and "equity" in equity_csv.columns:
                    bench = float(pd.to_numeric(equity_csv.iloc[-1]["equity"], errors="coerce") or 0.0)
                    equity_db = float(executor.capital)
                    if getattr(executor, "positions", None):
                        for code, pos in executor.positions.items():
                            qty = float(pos.get("quantity", 0) or 0)
                            px = _latest_price(code)
                            equity_db += qty * max(px, 0.0)
                    if bench > 0 and equity_db > 0:
                        gap = abs(equity_db - bench) / bench
                        tol = float(os.getenv("COMPLIANT_GAP_TOL", "0.10"))
                        if gap > tol:
                            logger.info("[daily_once] 发现与合规净值偏差 %.2f%% (>%.0f%%)，用合规交易回填DB以消除历史虚高。", gap*100, tol*100)
                            db_path = executor.db_path
                            try:
                                # 备份 DB
                                bkp = os.path.join(_project_root(), "data", "trade_history.backup.db")
                                if os.path.exists(db_path):
                                    import shutil
                                    shutil.copyfile(db_path, bkp)
                                conn3 = sqlite3.connect(db_path)
                                conn3.execute("DROP TABLE IF EXISTS trades")
                                conn3.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, etf_code TEXT, action TEXT, price REAL, quantity REAL, value REAL, capital_after REAL, reasoning TEXT)")
                                df_tr = pd.read_csv(trades_csv)
                                use_cols = ["date","etf_code","action","price","quantity","value","capital_after","reasoning"]
                                df_tr = df_tr[use_cols]
                                df_tr.to_sql("trades", conn3, if_exists="append", index=False)
                                conn3.commit()
                            finally:
                                if 'conn3' in locals():
                                    conn3.close()
                            # 重新按DB恢复（此时为合规交易）
                            executor.positions.clear()
                            executor.capital = 100000.0
                            executor.restore_state_from_db()
        except Exception as e:
            logger.warning("[daily_once] 合规对齐检查失败：%s", e)

    # Adapt to daily_task(executor, core_list, observe_list, daily_ai_limit)
    daily_task(executor, etf_list, [], daily_ai_limit)

    # 生成合规CSV（直接从DB导出），无需重仿真
    _export_compliant_csv_from_db()

    # 追加：导出 qlib 原始CSV + 计算因子（若模块可用）
    try:
        if qlib_export_main is not None:
            logger.info("[daily_once] qlib_adapter 导出原始CSV...")
            qlib_export_main(etf_list)
        else:
            logger.info("[daily_once] qlib_adapter 不可用，跳过导出。")
    except Exception as e:
        logger.warning("[daily_once] qlib_adapter 导出失败：%s", e)
    try:
        if qlib_factor_run is not None:
            logger.info("[daily_once] qlib_run 计算因子...")
            qlib_factor_run(etf_list)
        else:
            logger.info("[daily_once] qlib_run 不可用，跳过因子计算。")
    except Exception as e:
        logger.warning("[daily_once] qlib_run 因子计算失败：%s", e)

    # 追加：每日持仓盈亏快照
    try:
        from scripts.track_daily_pnl import main as track_pnl_main
        logger.info("[daily_once] 开始生成每日持仓盈亏快照...")
        track_pnl_main()
    except Exception as e:
        logger.warning("[daily_once] 生成每日持仓盈亏快照失败: %s", e)

    logger.info("[daily_once] 完成并退出。")


if __name__ == "__main__":
    main()

