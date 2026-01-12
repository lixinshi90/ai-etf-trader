from __future__ import annotations

import sqlite3
from pathlib import Path
import shutil
import time

DB_PATH = Path("data/trade_history.db")
DATE = "2025-12-25"
EQUITY = 100208.89


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")

    bkp = DB_PATH.with_suffix(DB_PATH.suffix + f".bak_ins_{DATE.replace('-', '')}_{int(time.time())}")
    shutil.copyfile(DB_PATH, bkp)
    print(f"[backup] {DB_PATH} -> {bkp}")

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")

        cur.execute("SELECT equity FROM daily_equity WHERE date = ?", (DATE,))
        row = cur.fetchone()
        if row:
            print(f"[before] {DATE} equity={float(row[0]):.2f}")
        else:
            print(f"[before] {DATE} not found")

        cur.execute(
            "INSERT INTO daily_equity(date, equity) VALUES(?, ?) "
            "ON CONFLICT(date) DO UPDATE SET equity=excluded.equity",
            (DATE, float(EQUITY)),
        )
        conn.commit()

        cur.execute("SELECT equity FROM daily_equity WHERE date = ?", (DATE,))
        row2 = cur.fetchone()
        print(f"[after] {DATE} equity={float(row2[0]):.2f}")

    finally:
        conn.close()

    print("\n[next] Web /api/performance caches 60s; refresh after ~60s or restart web server.")


if __name__ == "__main__":
    main()

