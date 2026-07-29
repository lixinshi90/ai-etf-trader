# -*- coding: utf-8 -*-
"""equity_guard.py

在“写入日终快照(daily_equity)”之前做源头加固：
- missing_px 非空或价格<=0：拒绝写入（防止持仓估值异常导致净值虚高/虚低）
- 单日净值变动 > 阈值（默认 5%）：拒绝写入（更贴合 ETF 低波动）
- 幂等：同一天已存在 daily_equity 记录时，默认拒绝覆盖（除非 allow_overwrite=True）

重要：
- 不能假设 trades.capital_after 与 daily_equity 使用同一“语义”。
  在本项目中，TradeExecutor.capital 表示“现金余额”，total equity = cash + holdings_value。
  因此：用于“单日跳变”比较的基准应当来自 "prev_cash + prev_holdings_value"，
  而不是简单使用 daily_equity(prev)。

该模块只负责校验与给出拒绝原因，不负责交易执行。

"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class EquityGuardResult:
    ok: bool
    reason: str
    prev_date: Optional[str] = None
    prev_equity: Optional[float] = None
    pct_change: Optional[float] = None


def _get_latest_equity(conn: sqlite3.Connection) -> Optional[Tuple[str, float]]:
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")
    cur.execute("SELECT date, equity FROM daily_equity ORDER BY date DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        return None
    try:
        return str(row[0]), float(row[1])
    except Exception:
        return None


def _date_exists(conn: sqlite3.Connection, date_str: str) -> bool:
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")
    cur.execute("SELECT 1 FROM daily_equity WHERE date = ? LIMIT 1", (date_str,))
    return cur.fetchone() is not None


def _infer_initial_cash_from_first_trade(rows: list[tuple]) -> Optional[float]:
    """从第一笔交易反推初始现金（与 replay_guard/restore_state 完全一致）。

    rows: (date, etf_code, action, quantity, value, reasoning, capital_after)
    """
    if not rows:
        return None
    _date, _code, act, _qty, gross, reasoning, cap_after = rows[0]
    try:
        act = str(act).lower().strip()
        gross = float(gross or 0.0)
        cap_after = float(cap_after or 0.0)
    except Exception:
        return None

    # 从 reasoning 解析成本: "成本: xx.xx"
    cost = 0.0
    try:
        import re
        m = re.search(r"成本:\s*([0-9]+(?:\.[0-9]+)?)", str(reasoning or ""))
        if m:
            cost = float(m.group(1))
    except Exception:
        cost = 0.0

    if gross <= 0 or cap_after <= 0:
        return None

    if act == 'buy':
        # cap_after = cash_before - (gross + cost)
        return cap_after + gross + cost
    if act == 'sell':
        # cap_after = cash_before + (gross - cost)
        return cap_after - gross + cost
    return None


def _get_prev_cash_from_trades(conn: sqlite3.Connection, prev_date: str, default_initial_capital: Optional[float] = None) -> Optional[float]:
    """用 trades 流水“完整回放”得到 prev_date 日终现金。

    重要：不再使用 capital_after 抄近道（它可能与真实现金语义不一致）。

    回放规则：
    - buy: cash -= gross + cost
    - sell: cash += gross - cost
    - cost 从 reasoning 中解析 "成本: xx.xx"，解析失败则视为 0

    若无法反推初始现金，则回退到 default_initial_capital（若给定）。
    """
    cur = conn.cursor()

    # 取截至 prev_date(含) 的所有交易（用于回放）
    cur.execute(
        "SELECT date, etf_code, action, quantity, value, reasoning, capital_after "
        "FROM trades WHERE datetime(date) <= datetime(?) ORDER BY datetime(date)",
        (prev_date + ' 23:59:59',),
    )
    rows = cur.fetchall()
    if not rows:
        return default_initial_capital

    init_cash = _infer_initial_cash_from_first_trade(rows)
    if init_cash is None:
        if default_initial_capital is None:
            return None
        init_cash = float(default_initial_capital)

    cash = float(init_cash)

    import re
    for _date, _code, act, _qty, gross, reasoning, _cap_after in rows:
        try:
            act = str(act).lower().strip()
            gross = float(gross or 0.0)
        except Exception:
            continue

        cost = 0.0
        try:
            m = re.search(r"成本:\s*([0-9]+(?:\.[0-9]+)?)", str(reasoning or ""))
            if m:
                cost = float(m.group(1))
        except Exception:
            cost = 0.0

        if act == 'buy':
            cash -= (gross + cost)
        elif act == 'sell':
            cash += (gross - cost)

    return float(cash)


def _get_positions_as_of(conn: sqlite3.Connection, as_of_date: str) -> Dict[str, float]:
    """用 trades 流水重建截至 as_of_date(含) 的持仓数量（净数量）。"""
    cur = conn.cursor()
    cur.execute(
        "SELECT etf_code, action, quantity FROM trades WHERE datetime(date) <= datetime(?) ORDER BY datetime(date)",
        (as_of_date + ' 23:59:59',),
    )
    positions: Dict[str, float] = {}
    for code, action, qty in cur.fetchall():
        if code is None:
            continue
        c = str(code).strip()
        if not c:
            continue
        act = str(action).lower().strip()
        try:
            q = float(qty or 0)
        except Exception:
            q = 0.0
        if act == 'sell':
            q = -q
        positions[c] = positions.get(c, 0.0) + q
    # 只保留正持仓
    positions = {c: q for c, q in positions.items() if q > 1e-9}
    return positions


def _read_close_price_as_of(etf_db_path: str, code: str, as_of_date: str) -> Optional[float]:
    """从 data/etf_data.db 读取截至 as_of_date 的最近收盘价（支持中文/英文列）。"""
    if not etf_db_path or (not os.path.exists(etf_db_path)):
        return None
    conn = sqlite3.connect(etf_db_path)
    try:
        # 优先中文表结构
        try:
            df = conn.execute(
                f"SELECT 收盘, 日期 FROM etf_{code} WHERE 日期 <= ? ORDER BY 日期 DESC LIMIT 1",
                (as_of_date,),
            ).fetchone()
            if df and df[0] is not None:
                return float(df[0])
        except Exception:
            pass
        # 回退英文结构
        try:
            df = conn.execute(
                f"SELECT close, date FROM etf_{code} WHERE date <= ? ORDER BY date DESC LIMIT 1",
                (as_of_date,),
            ).fetchone()
            if df and df[0] is not None:
                return float(df[0])
        except Exception:
            pass
        return None
    finally:
        conn.close()


def _estimate_prev_total_equity(
    trade_db_path: str,
    etf_db_path: str,
    prev_date: str,
    initial_capital: Optional[float] = None,
) -> Tuple[Optional[float], List[str]]:
    """估算 prev_date 的“基准总资产” = prev_cash + prev_holdings_value。

    返回 (prev_total_equity, missing_px_codes)
    """
    conn = sqlite3.connect(trade_db_path)
    try:
        prev_cash = _get_prev_cash_from_trades(conn, prev_date, default_initial_capital=initial_capital)
        if prev_cash is None:
            return None, []
        pos = _get_positions_as_of(conn, prev_date)
    finally:
        conn.close()

    missing = []
    holdings_value = 0.0
    for code, qty in pos.items():
        px = _read_close_price_as_of(etf_db_path, code, prev_date)
        if px is None or px <= 0:
            missing.append(code)
            continue
        holdings_value += float(qty) * float(px)

    return float(prev_cash) + float(holdings_value), missing


def guard_daily_equity_write(
    db_path: str,
    snapshot_date: str,
    final_equity: float,
    missing_px: List[str],
    max_daily_change_pct: float = 5.0,
    allow_overwrite: bool = False,
    etf_db_path: Optional[str] = None,
    initial_capital: Optional[float] = None,
    current_cash: Optional[float] = None,
) -> EquityGuardResult:
    """对“写日终快照”做源头拦截。

    max_daily_change_pct:
      - 5.0 表示 5%

    allow_overwrite:
      - False：同一天已有记录则拒绝（幂等保护）

    etf_db_path:
      - 用于读取 prev_date 收盘价，计算 prev_total_equity 作为跳变比较基准

    initial_capital / current_cash:
      - 用于“现金语义异常”快速拦截：若 current_cash 明显不可能（如 > initial_capital*2），拒绝写入。
    """

    # 0) 现金语义校验（防止把总资产错误写进 cash）
    if initial_capital is not None and current_cash is not None:
        try:
            ic = float(initial_capital)
            cc = float(current_cash)
            if ic > 0 and cc > ic * 2.0:
                return EquityGuardResult(False, f"现金语义异常：current_cash={cc:.2f} > initial_capital*2={ic*2:.2f}，拒绝写入")
        except Exception:
            pass

    # 1) 基础数值校验
    try:
        eq = float(final_equity)
    except Exception:
        return EquityGuardResult(False, f"final_equity 非法: {final_equity}")

    if eq <= 0:
        return EquityGuardResult(False, f"final_equity<=0，拒绝写入: {eq}")

    # 2) 价格缺失校验（当日）
    if missing_px:
        return EquityGuardResult(False, f"missing_px 非空({missing_px})，拒绝写入日终快照")

    # 3) DB 校验：同日幂等
    conn = sqlite3.connect(db_path)
    try:
        if (not allow_overwrite) and _date_exists(conn, snapshot_date):
            return EquityGuardResult(False, f"{snapshot_date} 已存在日终快照，幂等保护拒绝覆盖")

        latest = _get_latest_equity(conn)
        if latest is None:
            return EquityGuardResult(True, "ok(first snapshot)")
        prev_date, _prev_eq_unused = latest
    finally:
        conn.close()

    # 4) 用 prev_cash + prev_holdings_value 计算基准（避免 cash/equity 语义混淆）
    if etf_db_path:
        prev_total, prev_missing = _estimate_prev_total_equity(db_path, etf_db_path, prev_date, initial_capital=initial_capital)
        if prev_total is None:
            return EquityGuardResult(True, "ok(prev_total_unavailable)")
        if prev_missing:
            return EquityGuardResult(False, f"prev_date={prev_date} 估值缺失价格(prev_missing_px={prev_missing})，为安全起见拒绝写入")
        base = prev_total
    else:
        # 如果没提供 etf_db_path，则退回旧逻辑（不推荐，但保底）
        base = _prev_eq_unused

    if base is None or base <= 0:
        return EquityGuardResult(True, "ok(prev_base<=0 skipped)")

    pct = abs(eq - base) / base * 100.0
    if pct > float(max_daily_change_pct):
        return EquityGuardResult(
            False,
            f"单日净值变动 {pct:.2f}% > {max_daily_change_pct:.2f}% 阈值，疑似异常，拒绝写入",
            prev_date=prev_date,
            prev_equity=float(base),
            pct_change=pct,
        )

    return EquityGuardResult(True, "ok", prev_date=prev_date, prev_equity=float(base), pct_change=pct)
