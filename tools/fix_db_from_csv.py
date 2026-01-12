#!/usr/bin/env python3
"""
一键修复脚本：用重仿真CSV的真数据覆盖数据库中的虚高数据
支持：
1) UPSERT 覆盖 daily_equity（有则改、无则补，可指定截止日期）
2) 全量替换 trades 表（去 id 列、NaN->NULL），可通过 --skip-trades 跳过
3) 可配置 DB/CSV 路径、覆盖范围；带日志输出与异常处理

用法示例：
- 基础（覆盖 2025-12-15 前净值 + 全量替换交易）
  uv run python -m tools.fix_db_from_csv
- 全量覆盖净值（不限制日期）
  uv run python -m tools.fix_db_from_csv --cutoff None
- 仅修复净值，跳过交易
  uv run python -m tools.fix_db_from_csv --skip-trades
- 自定义路径
  uv run python -m tools.fix_db_from_csv --db data/trade_history.db --equity-csv out/resimulated_daily_equity.csv
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------- Logging ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("fix_db")

# ---------------- Defaults ----------------
DEFAULT_DB_PATH = Path("data/trade_history.db")
DEFAULT_EQUITY_CSV = Path("out/resimulated_daily_equity.csv")
DEFAULT_TRADES_CSV = Path("out/resimulated_trades_fully_compliant.csv")
DEFAULT_CUTOFF_DATE = "2025-12-15"  # 仅覆盖该日期之前的净值；传 None 则全量


def _parse_cutoff(arg: Optional[str]) -> Optional[str]:
    if arg is None:
        return DEFAULT_CUTOFF_DATE
    a = str(arg).strip()
    if a.lower() == "none" or a == "":
        return None
    return a


def backup_db(db_path: Path) -> bool:
    if not db_path.exists():
        logger.error("数据库文件不存在：%s", db_path)
        return False
    backup_path = db_path.with_suffix(".backup.db")
    try:
        backup_path.write_bytes(db_path.read_bytes())
        logger.info("数据库已备份至：%s", backup_path)
        return True
    except Exception as e:
        logger.error("备份数据库失败：%s", e)
        return False


def upsert_daily_equity(db_path: Path, csv_path: Path, cutoff_date: Optional[str]) -> bool:
    if not csv_path.exists():
        logger.error("净值CSV文件不存在：%s", csv_path)
        return False
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            logger.warning("净值CSV为空：%s", csv_path)
            return True
        # 标准化日期
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df.dropna(subset=["date"])  # 去除无效日期
        if cutoff_date:
            mask = pd.to_datetime(df["date"]) < pd.to_datetime(cutoff_date)
            df = df[mask]
            logger.info("仅处理 %s 之前的净值数据：%d 行", cutoff_date, len(df))
        else:
            logger.info("全量处理净值数据：%d 行", len(df))
        if df.empty:
            logger.info("待写入的净值数据为空，跳过。")
            return True
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_equity (
                    date TEXT PRIMARY KEY,
                    equity REAL
                )
                """
            )
            upsert_sql = (
                "INSERT INTO daily_equity(date,equity) VALUES(?,?) "
                "ON CONFLICT(date) DO UPDATE SET equity=excluded.equity"
            )
            data = [(str(r["date"]), float(r["equity"])) for _, r in df.iterrows()]
            conn.executemany(upsert_sql, data)
            conn.commit()
        finally:
            conn.close()
        logger.info("成功 UPSERT %d 行到 daily_equity", len(df))
        return True
    except Exception as e:
        logger.error("覆盖 daily_equity 失败：%s", e)
        return False


def replace_trades(db_path: Path, csv_path: Path) -> bool:
    if not csv_path.exists():
        logger.error("交易CSV文件不存在：%s", csv_path)
        return False
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            logger.warning("交易CSV为空：%s", csv_path)
            return True
        # 去 id 列，NaN->None
        if "id" in df.columns:
            df = df.drop(columns=["id"])  # 让 SQLite 自增
        df = df.where(pd.notna(df), None)
        logger.info("处理交易数据：%d 行 (已去id/NaN->NULL)", len(df))
        conn = sqlite3.connect(db_path)
        try:
            # 直接替换 trades 表结构，以 DF 列为准，确保兼容
            # 先丢弃旧表
            conn.execute("DROP TABLE IF EXISTS trades")
            conn.commit()
            # 再用 DF 创建新表
            df.to_sql("trades", conn, if_exists="replace", index=False)
            conn.commit()
        finally:
            conn.close()
        logger.info("成功替换 trades 表为 %d 行", len(df))
        return True
    except Exception as e:
        logger.error("替换 trades 失败：%s", e)
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="用重仿真CSV修复数据库虚高数据（DB优先方案）")
    p.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="数据库路径，默认 data/trade_history.db")
    p.add_argument("--equity-csv", type=Path, default=DEFAULT_EQUITY_CSV, help="净值CSV路径，默认 out/resimulated_daily_equity.csv")
    p.add_argument("--trades-csv", type=Path, default=DEFAULT_TRADES_CSV, help="交易CSV路径，默认 out/resimulated_trades_fully_compliant.csv")
    p.add_argument("--cutoff", type=str, default=DEFAULT_CUTOFF_DATE, help="仅覆盖该日期之前的净值；传 None 表示全量")
    p.add_argument("--skip-trades", action="store_true", help="跳过 trades 表替换，仅修复净值")
    args = p.parse_args()

    cutoff = _parse_cutoff(args.cutoff)

    # 1) 备份 DB
    if not backup_db(args.db):
        return 1

    # 2) UPSERT daily_equity
    if not upsert_daily_equity(args.db, args.equity_csv, cutoff):
        return 1

    # 3) 替换 trades（可跳过）
    if not args.skip_trades:
        if not replace_trades(args.db, args.trades_csv):
            return 1

    logger.info("=== 数据库修复完成！请重启 Web 并验证 ===")
    logger.info("资产曲线: http://127.0.0.1:5001/api/performance")
    logger.info("交易记录: http://127.0.0.1:5001/api/trades")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

