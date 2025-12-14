# -*- coding: utf-8 -*-
"""
从 decisions JSON 文件回填交易流水到 data/trade_history.db。

功能：
- 读取一个包含 `decisions` 列表的 JSON 文件。
- 可选 `--as-yesterday`，将所有交易日期强制覆盖为昨天。
- 基于 .env 交易参数（滑点/成本/动态仓位）计算成交价与数量。
- 在 trades 表插入流水，并 upsert 当日日终净值到 daily_equity。
- 不改动其他日期的数据。

用法：
  # 1. 先生成决策文件（例如用 qlib topk）
  uv run python -m scripts.qlib_today_topk --write-json

  # 2. 将该决策文件回填到昨天
  uv run python -m scripts.backfill_from_decisions --file decisions/qlib_topk_20251211.json --as-yesterday

  # 3. 或回填到指定日期
  uv run python -m scripts.backfill_from_decisions --file decisions/qlib_topk_20251211.json --date 2025-12-11
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Tuple, List

import pandas as pd
from dotenv import load_dotenv

# Reuse helpers from backfill_trades_from_log
from scripts.backfill_trades_from_log import (
    read_prev_state,
    get_close_price,
    compute_position_pct,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TRADE_DB = os.path.join(ROOT, "data", "trade_history.db")


def main():
    load_dotenv(override=True)
    ap = argparse.ArgumentParser(description="从 decisions JSON 回填交易")
    ap.add_argument("--file", required=True, help="包含 decisions 列表的 JSON 文件路径")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--as-yesterday", action="store_true", help="将交易日期强制覆盖为昨天")
    g.add_argument("--date", type=str, help="YYYY-MM-DD，将交易日期强制覆盖为该日")
    ap.add_argument("--dry-run", action="store_true", help="不写入数据库")
    args = ap.parse_args()

    if args.as_yesterday:
        target_date = (datetime.now().date() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
            target_date = args.date
        except Exception:
            raise SystemExit("--date 必须是 YYYY-MM-DD")

    # 读取决策文件
    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)
    decisions = data.get("decisions", [])
    if not decisions:
        raise SystemExit(f"{args.file} 中未找到 'decisions' 列表")

    # 读取交易参数
    init_cap = float(os.getenv("INITIAL_CAPITAL", "100000"))
    enable_dyn = os.getenv("ENABLE_DYNAMIC_POSITION", "false").lower() == "true"
    base_pos = float(os.getenv("BASE_POSITION_PCT", "0.2"))
    min_pos = float(os.getenv("MIN_POSITION_PCT", "0.05"))
    max_pos = float(os.getenv("MAX_POSITION_PCT", "0.3"))
    cost_bps = float(os.getenv("COST_BPS", "5"))
    slip_bps = float(os.getenv("SLIPPAGE_BPS", "2"))

    # 读取前一时刻账户状态
    cash, pos = read_prev_state(target_date + " 00:00:00", init_cap)
    print(f"[state-before] date={target_date}, cash={cash:.2f}, positions={ {k: round(v,4) for k,v in pos.items()} }")

    # 打开交易库
    os.makedirs(os.path.dirname(TRADE_DB), exist_ok=True)
    conn = sqlite3.connect(TRADE_DB)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, etf_code TEXT, action TEXT, price REAL, quantity REAL, value REAL, capital_after REAL, reasoning TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")
        made = 0
        skipped = 0
        for dec in decisions:
            action = str(dec.get("decision", "hold")).lower()
            if action == "hold":
                continue
            code = str(dec.get("etf_code"))
            conf = float(dec.get("confidence", 0.5))
            reason = str(dec.get("reasoning", ""))
            px = get_close_price(code, target_date)
            if not px or px <= 0:
                skipped += 1; continue
            exec_px = float(px) * (1.0 + (slip_bps/10000.0 if action == "buy" else -slip_bps/10000.0))
            ts = f"{target_date} 15:00:00"

            if action == "buy":
                pct = compute_position_pct(conf, enable_dyn, base_pos, min_pos, max_pos)
                budget = cash * pct
                if budget <= 0: skipped += 1; continue
                qty = budget / exec_px
                gross = qty * exec_px
                cost = gross * (cost_bps/10000.0)
                total_out = gross + cost
                if total_out > cash: # 资金不足时，按最大可用现金调整
                    qty = max(0.0, (cash / (1.0 + cost_bps/10000.0)) / exec_px)
                    gross = qty * exec_px; cost = gross * (cost_bps/10000.0); total_out = gross + cost
                if qty <= 0 or total_out <= 0: skipped += 1; continue
                cash -= total_out
                pos[code] = pos.get(code, 0.0) + qty
                if not args.dry_run:
                    conn.execute("INSERT INTO trades(date, etf_code, action, price, quantity, value, capital_after, reasoning) VALUES (?,?,?,?,?,?,?,?)", (ts, code, "buy", exec_px, qty, gross, cash, reason))
                made += 1
            elif action == "sell":
                qty_have = float(pos.get(code, 0.0))
                if qty_have <= 1e-9: skipped += 1; continue
                qty = qty_have
                gross = qty * exec_px
                cost = gross * (cost_bps/10000.0)
                net_in = gross - cost
                cash += net_in
                pos[code] = 0.0
                if not args.dry_run:
                    conn.execute("INSERT INTO trades(date, etf_code, action, price, quantity, value, capital_after, reasoning) VALUES (?,?,?,?,?,?,?,?)", (ts, code, "sell", exec_px, qty, gross, cash, reason))
                made += 1

        # 计算日终总净值
        holdings_value = 0.0
        for code, qty in pos.items():
            if qty > 1e-9:
                px = get_close_price(code, target_date)
                if px and px > 0:
                    holdings_value += qty * px
        final_equity = cash + holdings_value

        if not args.dry_run:
            # upsert 当日 daily_equity
            conn.execute("INSERT INTO daily_equity(date, equity) VALUES(?,?) ON CONFLICT(date) DO UPDATE SET equity=excluded.equity", (target_date, final_equity))
            conn.commit()
        print(f"[backfill-decisions] done. inserted={made}, skipped={skipped}. final_equity={final_equity:.2f}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
