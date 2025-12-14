# -*- coding: utf-8 -*-
from __future__ import annotations
"""
一次性执行每日任务：拉数 -> 风控 -> AI决策 -> 交易 -> 日志 -> 退出。
用于 Windows 任务计划程序或任意定时器按天调度。
用法：
    conda run -n ai-etf-trader python -m src.daily_once
"""
import os
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


def main():
    load_dotenv(override=True)
    _setup_logging_once()

    logger = logging.getLogger("once")
    logger.info("[daily_once] 启动一次性每日任务...")

    default_etfs = ["510050", "159915", "510300"]
    etf_list = _parse_etf_list(os.getenv("ETF_LIST"), default_etfs)

    try:
        daily_ai_limit = int(os.getenv("DAILY_AI_CALLS_LIMIT", str(len(etf_list))))
    except Exception:
        daily_ai_limit = len(etf_list)

    executor = TradeExecutor(initial_capital=100000.0)
    # 恢复上一次交易后的账户与持仓，保证从前一日状态继续
    try:
        executor.restore_state_from_db()
    except Exception:
        pass
    # Adapt to daily_task(executor, core_list, observe_list, daily_ai_limit)
    daily_task(executor, etf_list, [], daily_ai_limit)

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

    logger.info("[daily_once] 完成并退出。")


if __name__ == "__main__":
    main()

