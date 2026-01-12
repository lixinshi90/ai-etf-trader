# -*- coding: utf-8 -*-
"""
从 logs/daily.log 回填某一自然日的交易流水到 data/trade_history.db。
规则：
- 解析指定日期的 "<code> AI决策: <buy|sell|hold> (置信度: x.xx)" 记录
- 使用 .env 中的交易参数（动态仓位、成本、滑点、仓位上下限）
- 价格采用 etf_data.db 当天收盘价（无则用最近一条收盘价），买入加滑点，卖出减滑点
- 成交额计入成本（COST_BPS），并更新现金；卖出时若无持仓则跳过
- 若同一日期、同一标的、同一方向的流水已存在，默认跳过（可 --force 覆盖）

用法：
  uv run python -m scripts.backfill_trades_from_log --date 2025-12-09
  uv run python -m scripts.backfill_trades_from_log --date 2025-12-09 --dry-run
  uv run python -m scripts.backfill_trades_from_log --date 2025-12-09 --force
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Tuple, List

import pandas as pd
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TRADE_DB = os.path.join(ROOT, "data", "trade_history.db")
ETF_DB = os.path.join(ROOT, "data", "etf_data.db")
LOG_FILE = os.path.join(ROOT, "logs", "daily.log")

AI_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) .*? (\d{6}) AI决策: (buy|sell|hold) \(置信度: ([0-9.]+)\)")


def read_ai_decisions(target_date: str) -> List[Tuple[str, str, float]]:
    out: List[Tuple[str, str, float]] = []
    if not os.path.exists(LOG_FILE):
        return out
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            m = AI_LINE_RE.match(line.strip())
            if not m:
                continue
            d, code, action, conf = m.group(1), m.group(2), m.group(3), float(m.group(4))
            if d == target_date:
                out.append((code, action.lower(), conf))
    return out


def get_close_price(code: str, day: str) -> float | None:
    if not os.path.exists(ETF_DB):
        return None
    conn = sqlite3.connect(ETF_DB)
    try:
        try:
            df = pd.read_sql_query(f"SELECT * FROM etf_{code}", conn)
        except Exception:
            return None
    finally:
        conn.close()
    if df is None or df.empty:
        return None
    date_col = None
    for c in ("日期", "date", "Date"):
        if c in df.columns:
            date_col = c
            break
    px_col = None
    for c in ("收盘", "收盘价", "close", "Close"):
        if c in df.columns:
            px_col = c
            break
    if not date_col or not px_col:
        return None
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)
    target = pd.to_datetime(day)
    # 当天优先，否则取当天之前最近一条
    df2 = df[df[date_col] == target]
    if df2.empty:
        df2 = df[df[date_col] <= target]
        if df2.empty:
            return None
        px = df2.iloc[-1][px_col]
    else:
        px = df2.iloc[-1][px_col]
    try:
        return float(px)
    except Exception:
        return None


def read_prev_state(as_of_date: str, init_cap: float) -> Tuple[float, Dict[str, float]]:
    """读取 as_of_date 当天 0 点之前的账户状态（现金与持仓数量）。"""
    cash = float(init_cap)
    pos: Dict[str, float] = {}
    if not os.path.exists(TRADE_DB):
        return cash, pos
    conn = sqlite3.connect(TRADE_DB)
    try:
        # 读取 as_of_date 之前的所有交易
        q = "SELECT date, etf_code, action, price, quantity, value, capital_after FROM trades ORDER BY datetime(date)"
        df = pd.read_sql_query(q, conn)
    finally:
        conn.close()
    if df is None or df.empty:
        return cash, pos
    df["dt"] = pd.to_datetime(df["date"], errors="coerce")
    cutoff = pd.to_datetime(as_of_date)
    df = df[df["dt"] < cutoff]
    if df.empty:
        return cash, pos
    # 优先使用最后一条 capital_after 作为现金
    if df["capital_after"].notna().any():
        cash = float(df["capital_after"].dropna().iloc[-1])
    # 按交易重建持仓
    for _, r in df.iterrows():
        code = str(r["etf_code"]).strip()
        act = str(r["action"]).lower()
        qty = float(r.get("quantity", 0) or 0)
        if not code:
            continue
        if act == "buy":
            pos[code] = pos.get(code, 0.0) + qty
        elif act == "sell":
            pos[code] = pos.get(code, 0.0) - qty
    # 清零小量
    pos = {k: v for k, v in pos.items() if abs(v) > 1e-9}
    return cash, pos


def compute_position_pct(conf: float, enable_dyn: bool, base: float, lo: float, hi: float) -> float:
    pct = base
    if enable_dyn:
        pct = base * (0.5 + 0.5 * float(conf))
    return max(lo, min(hi, pct))


def backfill(date_str: str, dry_run: bool = False, force: bool = False) -> None:
    load_dotenv(override=True)
    init_cap = float(os.getenv("INITIAL_CAPITAL", "100000"))
    enable_dyn = os.getenv("ENABLE_DYNAMIC_POSITION", "false").lower() == "true"
    base_pos = float(os.getenv("BASE_POSITION_PCT", "0.2"))
    min_pos = float(os.getenv("MIN_POSITION_PCT", "0.05"))
    max_pos = float(os.getenv("MAX_POSITION_PCT", "0.3"))
    cost_bps = float(os.getenv("COST_BPS", "5"))
    slip_bps = float(os.getenv("SLIPPAGE_BPS", "2"))

    # 读取该日 AI 决策
    decs = read_ai_decisions(date_str)
    if not decs:
        print(f"[backfill-trades] {date_str} 日志中未找到 AI 决策，退出。")
        return

    # 读取前一时刻账户状态
    cash, pos = read_prev_state(date_str + " 00:00:00", init_cap)

    print(f"[state-before] date={date_str}, cash={cash:.2f}, positions={ {k: round(v,4) for k,v in pos.items()} }")

    # 打开交易库
    os.makedirs(os.path.dirname(TRADE_DB), exist_ok=True)
    conn = sqlite3.connect(TRADE_DB)
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
        made = 0
        skipped = 0
        for code, action, conf in decs:
            if action == "hold":
                continue
            # 重复判断（同日同code同向）
            if not force:
                cur = conn.execute(
                    "SELECT 1 FROM trades WHERE date LIKE ? AND etf_code=? AND action=? LIMIT 1",
                    (date_str + "%", code, action),
                ).fetchone()
                if cur:
                    skipped += 1
                    continue
            px = get_close_price(code, date_str)
            if not px or px <= 0:
                skipped += 1
                continue
            # 滑点处理
            exec_px = float(px) * (1.0 + (slip_bps/10000.0 if action == "buy" else -slip_bps/10000.0))
            # 时间戳取收盘 15:00:00
            ts = f"{date_str} 15:00:00"
            if action == "buy":
                pct = compute_position_pct(conf, enable_dyn, base_pos, min_pos, max_pos)
                budget = cash * pct
                if budget <= 0:
                    skipped += 1
                    continue
                qty = budget / exec_px
                gross = qty * exec_px
                cost = gross * (cost_bps/10000.0)
                total_out = gross + cost
                if total_out > cash:
                    # 降低到最大可用现金
                    qty = max(0.0, (cash / (1.0 + cost_bps/10000.0)) / exec_px)
                    gross = qty * exec_px
                    cost = gross * (cost_bps/10000.0)
                    total_out = gross + cost
                if qty <= 0 or total_out <= 0:
                    skipped += 1
                    continue
                cash -= total_out
                pos[code] = pos.get(code, 0.0) + qty
                if not dry_run:
                    conn.execute(
                        "INSERT INTO trades(date, etf_code, action, price, quantity, value, capital_after, reasoning) VALUES (?,?,?,?,?,?,?,?)",
                        (ts, code, "buy", float(exec_px), float(qty), float(gross), float(cash), f"backfill from log @conf={conf:.2f}")
                    )
                made += 1
            elif action == "sell":
                qty_have = float(pos.get(code, 0.0))
                if qty_have <= 1e-9:
                    skipped += 1
                    continue
                qty = qty_have
                gross = qty * exec_px
                cost = gross * (cost_bps/10000.0)
                net_in = gross - cost
                cash += net_in
                pos[code] = 0.0
                if not dry_run:
                    conn.execute(
                        "INSERT INTO trades(date, etf_code, action, price, quantity, value, capital_after, reasoning) VALUES (?,?,?,?,?,?,?,?)",
                        (ts, code, "sell", float(exec_px), float(qty), float(gross), float(cash), f"backfill from log @conf={conf:.2f}")
                    )
                made += 1
        if not dry_run:
            conn.commit()
        print(f"[backfill-trades] done. inserted={made}, skipped={skipped}. cash_end={cash:.2f}")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Backfill trades from daily.log for a given date")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="Do not write DB")
    ap.add_argument("--force", action="store_true", help="Insert even if same-day same-code same-action exists")
    args = ap.parse_args()

    # 安全性：只允许日期在 [1970, 2100)
    try:
        d = datetime.strptime(args.date, "%Y-%m-%d")
        if not (1970 <= d.year < 2100):
            raise ValueError
    except Exception:
        raise SystemExit("--date 需为 YYYY-MM-DD")

    backfill(args.date, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()

