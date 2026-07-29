from __future__ import annotations

import sqlite3
from pathlib import Path
import shutil
import time

DB_PATH = Path("data/trade_history.db")
TARGET_DAY = "2025-12-24"
NEW_CAPITAL_AFTER = 42346.25


def _get_columns(cur: sqlite3.Cursor, table: str) -> list[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return [str(r[1]) for r in cur.fetchall()]


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")

    # backup
    bkp = DB_PATH.with_suffix(DB_PATH.suffix + f".bak_capital_after_{TARGET_DAY.replace('-', '')}_{int(time.time())}")
    shutil.copyfile(DB_PATH, bkp)
    print(f"[backup] {DB_PATH} -> {bkp}")

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()

        # Ensure trades exists (do NOT change schema if it already exists)
        cur.execute(
            "CREATE TABLE IF NOT EXISTS trades (date TEXT, etf_code TEXT, action TEXT, price REAL, quantity REAL, value REAL, capital_after REAL, reasoning TEXT)"
        )

        cols = _get_columns(cur, "trades")
        if "capital_after" not in cols:
            raise RuntimeError(f"trades table has no capital_after column. cols={cols}")

        # Choose a row identifier if present
        rowid_expr = "rowid"
        if "id" in cols:
            rowid_expr = "id"

        # Prefer: last trade on TARGET_DAY (by datetime)
        cur.execute(
            f"SELECT {rowid_expr}, date, etf_code, action, capital_after FROM trades WHERE date LIKE ? ORDER BY datetime(date) DESC LIMIT 1",
            (TARGET_DAY + "%",),
        )
        row = cur.fetchone()

        if row is None:
            # Fallback: last trade before end of TARGET_DAY
            cur.execute(
                f"SELECT {rowid_expr}, date, etf_code, action, capital_after FROM trades WHERE datetime(date) < datetime(?) ORDER BY datetime(date) DESC LIMIT 1",
                (TARGET_DAY + " 23:59:59",),
            )
            row = cur.fetchone()

        if row is None:
            raise RuntimeError(f"No trade rows found on/before {TARGET_DAY}; cannot set capital_after baseline")

        key, dt, code, action, old_capital = row
        try:
            old_capital_f = float(old_capital) if old_capital is not None else None
        except Exception:
            old_capital_f = None

        print(f"[target] key({rowid_expr})={key} date={dt} etf_code={code} action={action} capital_after(before)={old_capital_f}")

        cur.execute(
            f"UPDATE trades SET capital_after = ? WHERE {rowid_expr} = ?",
            (float(NEW_CAPITAL_AFTER), key),
        )
        conn.commit()

        cur.execute(f"SELECT capital_after FROM trades WHERE {rowid_expr} = ?", (key,))
        new_val = cur.fetchone()
        print(f"[after] key({rowid_expr})={key} capital_after={float(new_val[0]):.2f}")

    finally:
        conn.close()

    print("\n[next] Re-run daily task:")
    print("  python -m src.daily_once")


if __name__ == "__main__":
    main()
