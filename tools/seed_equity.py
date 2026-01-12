#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seed (insert if missing) a starting equity row into data/trade_history.db daily_equity.
Usage examples:
  uv run python -m tools.seed_equity                 # default: --date 2025-11-26, equity from config.yaml
  uv run python -m tools.seed_equity --date 2025-11-26
  uv run python -m tools.seed_equity --date 2025-11-26 --equity 100000
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import sys

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

def load_initial_capital(cfg_path: Path, fallback: float = 100000.0) -> float:
    if not cfg_path.exists() or yaml is None:
        return float(fallback)
    try:
        with cfg_path.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        return float((data.get('strategy') or {}).get('initial_capital', fallback))
    except Exception:
        return float(fallback)


def main() -> int:
    p = argparse.ArgumentParser(description='Seed a starting equity row into daily_equity table')
    p.add_argument('--db', type=Path, default=Path('data/trade_history.db'), help='Path to trade_history.db')
    p.add_argument('--config', type=Path, default=Path('config.yaml'), help='Path to config.yaml')
    p.add_argument('--date', type=str, default='2025-11-26', help='Date to seed, e.g. 2025-11-26')
    p.add_argument('--equity', type=float, default=None, help='Equity to seed; if omitted, read from config.yaml strategy.initial_capital')
    args = p.parse_args()

    eq = float(args.equity) if args.equity is not None else load_initial_capital(args.config)

    conn = sqlite3.connect(str(args.db))
    try:
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)')
        cur.execute('INSERT OR IGNORE INTO daily_equity(date, equity) VALUES (?, ?)', (args.date, eq))
        conn.commit()
    finally:
        conn.close()

    print(f"seeded {args.date} with equity {eq}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

