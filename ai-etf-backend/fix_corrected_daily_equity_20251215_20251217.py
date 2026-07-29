#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_corrected_daily_equity_20251215_20251217.py

用“真实口径（trade_history.db 的现金+持仓按收盘价估值）”修正 out/corrected_daily_equity.csv
中 2025-12-15~2025-12-17 的虚高值。

本脚本会：
1) 备份 out/corrected_daily_equity.csv -> out/corrected_daily_equity.csv.bak_fix
2) 对目标日期列表逐日重建 total
3) 覆盖写回 corrected_daily_equity.csv 对应日期的 equity（不存在则追加）
4) 为避免 Windows 下文件被占用导致 PermissionError，采用“写临时文件再原子替换”的方式落盘。

运行：
  cd "D:\\Quantitative Trading\\ai-etf-trader"
  python fix_corrected_daily_equity_20251215_20251217.py

"""

from __future__ import annotations

import os
import shutil
import sqlite3
from typing import Dict, Optional

import pandas as pd

TRADE_DB = os.path.join('data', 'trade_history.db')
ETF_DB = os.path.join('data', 'etf_data.db')
CSV_PATH = os.path.join('out', 'corrected_daily_equity.csv')
BAK_PATH = os.path.join('out', 'corrected_daily_equity.csv.bak_fix')
TMP_PATH = os.path.join('out', 'corrected_daily_equity.csv.tmp')

TARGET_DATES = ['2025-12-15', '2025-12-16', '2025-12-17']


def _cash_asof(con: sqlite3.Connection, day: str) -> Optional[float]:
    cur = con.cursor()
    cur.execute(
        "SELECT capital_after FROM trades WHERE datetime(date) <= datetime(?) ORDER BY datetime(date) DESC LIMIT 1",
        (day + ' 23:59:59',),
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def _positions_asof(con: sqlite3.Connection, day: str) -> Dict[str, float]:
    cur = con.cursor()
    cur.execute(
        "SELECT etf_code, action, quantity FROM trades WHERE datetime(date) <= datetime(?) ORDER BY datetime(date)",
        (day + ' 23:59:59',),
    )
    pos: Dict[str, float] = {}
    for code, act, qty in cur.fetchall():
        c = str(code).strip()
        if not c:
            continue
        a = str(act).lower().strip()
        try:
            q = float(qty or 0)
        except Exception:
            q = 0.0
        if a == 'sell':
            q = -q
        pos[c] = pos.get(c, 0.0) + q
    pos = {c: q for c, q in pos.items() if q > 1e-9}
    return pos


def _close_asof(code: str, day: str) -> Optional[float]:
    if not os.path.exists(ETF_DB):
        return None
    con = sqlite3.connect(ETF_DB)
    try:
        try:
            row = con.execute(
                f"SELECT 收盘 FROM etf_{code} WHERE 日期 <= ? ORDER BY 日期 DESC LIMIT 1",
                (day,),
            ).fetchone()
            if row and row[0] is not None:
                px = float(row[0])
                return px if px > 0 else None
        except Exception:
            pass
        try:
            row = con.execute(
                f"SELECT close FROM etf_{code} WHERE date <= ? ORDER BY date DESC LIMIT 1",
                (day,),
            ).fetchone()
            if row and row[0] is not None:
                px = float(row[0])
                return px if px > 0 else None
        except Exception:
            pass
        return None
    finally:
        con.close()


def calc_total(day: str) -> float:
    tcon = sqlite3.connect(TRADE_DB)
    try:
        cash = _cash_asof(tcon, day)
        if cash is None:
            cash = float(os.getenv('INITIAL_CAPITAL', '100000'))
        pos = _positions_asof(tcon, day)
    finally:
        tcon.close()

    hv = 0.0
    missing = []
    for code, qty in pos.items():
        px = _close_asof(code, day)
        if px is None:
            missing.append(code)
            continue
        hv += qty * px

    if missing:
        print(f'[WARN] {day} missing prices codes={missing} (these positions will be skipped in valuation)')

    return float(cash) + float(hv)


def atomic_write_csv(df: pd.DataFrame, dst_path: str, tmp_path: str) -> None:
    # 写到临时文件
    df.to_csv(tmp_path, index=False, encoding='utf-8-sig')
    # 用 replace 原子替换（Windows 下更稳）
    os.replace(tmp_path, dst_path)


def main():
    if not os.path.exists(CSV_PATH):
        raise SystemExit(f'missing {CSV_PATH}')
    if not os.path.exists(TRADE_DB):
        raise SystemExit('missing data/trade_history.db')
    if not os.path.exists(ETF_DB):
        raise SystemExit('missing data/etf_data.db')

    shutil.copy2(CSV_PATH, BAK_PATH)
    print('[fix] backup:', BAK_PATH)

    df = pd.read_csv(CSV_PATH)
    if df.empty or 'date' not in df.columns or 'equity' not in df.columns:
        raise SystemExit('corrected_daily_equity.csv format invalid (need date,equity)')

    df['date'] = df['date'].astype(str)
    old_map = {r['date']: float(r['equity']) for _, r in df.iterrows() if pd.notna(r.get('equity'))}

    updates = {}
    for d in TARGET_DATES:
        new_eq = calc_total(d)
        updates[d] = new_eq

    for d, new_eq in updates.items():
        old_eq = old_map.get(d)
        if old_eq is None:
            df = pd.concat([df, pd.DataFrame([{'date': d, 'equity': new_eq}])], ignore_index=True)
            print(f'[fix] add {d}: {new_eq:.2f}')
        else:
            df.loc[df['date'] == d, 'equity'] = new_eq
            print(f'[fix] update {d}: {old_eq:.2f} -> {new_eq:.2f}')

    df = df.sort_values('date').reset_index(drop=True)

    try:
        atomic_write_csv(df, CSV_PATH, TMP_PATH)
        print('[fix] wrote:', CSV_PATH)
    except PermissionError as e:
        print(f"[fix] PermissionError writing {CSV_PATH}: {e}")
        print('[fix] 可能原因：文件被 Excel/编辑器占用。请先关闭占用该文件的程序后重试。')
        print(f'[fix] 临时文件将写到: {TMP_PATH}（若存在可手动替换）')
        # 尝试至少把 tmp 写出来，便于手动替换
        try:
            df.to_csv(TMP_PATH, index=False, encoding='utf-8-sig')
            print('[fix] wrote tmp:', TMP_PATH)
        except Exception:
            pass
        raise


if __name__ == '__main__':
    main()
