# -*- coding: utf-8 -*-
"""
为指定历史日期重跑一次完整的每日任务。

功能:
- 接受 --date YYYY-MM-DD 参数。
- 拉取截至该日期的历史数据。
- 调用 AI/规则/合议生成决策。
- 将交易记录时间戳强制设为该日 15:00:00。
- 将日终绩效快照写入该日。

用法:
  # 为昨天跑一次完整的每日任务
  uv run python -m scripts.run_daily_for_date --date 2025-12-11

注意:
- 本脚本会真实调用 AI 模型并产生费用。
- 会真实写入 trades 和 daily_equity，请先备份 DB。
- 依赖 .env 中的配置（API KEY, ETF_LIST, 策略等）。
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, time

import pandas as pd
from dotenv import load_dotenv

# 确保能从 src 导入
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.main import (
    _parse_etf_list,
    _project_root,
    _ensure_dir,
    _etf_db_path,
    filter_etf_pool,
    get_rule_decision,
    ensemble_decision,
    validate_decision,
)
from src.trade_executor import TradeExecutor
from src.data_fetcher import fetch_etf_data, save_to_db


def _setup_logging_once():
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
    logger.handlers = [ch, fh]


def main(target_date_str: str):
    load_dotenv(override=True)
    _setup_logging_once()
    logger = logging.getLogger("backfill-task")
    logger.info(f"[backfill-task] 为日期 {target_date_str} 启动一次性任务...")

    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    # 1. 配置与数据准备
    default_etfs = ["510050", "159915", "510300"]
    core_etfs = _parse_etf_list(os.getenv("CORE_ETF_LIST", os.getenv("ETF_LIST")), default_etfs)
    observe_etfs = _parse_etf_list(os.getenv("OBSERVE_ETF_LIST"), [])

    core_etfs = filter_etf_pool(core_etfs)
    observe_etfs = filter_etf_pool(observe_etfs)
    all_etfs = sorted(list(set(core_etfs + observe_etfs)))

    # 拉取截至目标日的数据
    for etf in all_etfs:
        try:
            df = fetch_etf_data(etf, days=700, end_date=target_date.strftime("%Y%m%d"))
            save_to_db(df, etf, db_path=_etf_db_path())
            logger.info(f"已更新 {etf} 截至 {target_date_str} 的数据")
        except Exception as e:
            logger.warning(f"更新 {etf} 失败: {e}")

    # 2. 初始化交易执行器（强制日期）
    executor = TradeExecutor(initial_capital=float(os.getenv("INITIAL_CAPITAL", "100000")))
    # 恢复截至目标日期前的状态
    executor.restore_state_from_db(as_of_date=target_date.strftime("%Y-%m-%d"))
    executor.force_trade_timestamp = datetime.combine(target_date, time(15, 0, 0))

    # 3. 决策与交易
    # ... 此处复用 src.main.py 中的 daily_task 核心逻辑 ...
    # 为避免代码重复，此处直接调用一个修改版的 daily_task
    # 在实际项目中，应将 daily_task 重构为更通用的函数
    from src.main import daily_task
    try:
        daily_ai_limit = int(os.getenv("DAILY_AI_CALLS_LIMIT", str(len(all_etfs))))
    except Exception:
        daily_ai_limit = len(all_etfs)

    # 运行修改版的 daily_task
    daily_task(executor, core_etfs, observe_etfs, daily_ai_limit, force_date=target_date)

    # 追加：为回填日期导出 qlib 原始CSV + 计算因子
    try:
        from src.qlib_adapter import main as qlib_export_main
        logger.info("[backfill-task] qlib_adapter 导出原始CSV...")
        qlib_export_main(all_etfs)
    except Exception as e:
        logger.warning(f"[backfill-task] qlib_adapter 导出失败: {e}")
    try:
        from src.qlib_run import run as qlib_factor_run
        logger.info("[backfill-task] qlib_run 计算因子...")
        qlib_factor_run(all_etfs)
    except Exception as e:
        logger.warning(f"[backfill-task] qlib_run 因子计算失败: {e}")

    logger.info(f"[backfill-task] {target_date_str} 任务完成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="为指定历史日期重跑一次完整的每日任务")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD 格式的日期")
    args = parser.parse_args()
    main(args.date)

