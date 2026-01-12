from __future__ import annotations

import sqlite3
from pathlib import Path
import shutil
import time

DB_PATH = Path("data/trade_history.db")
DATES_TO_DELETE = ["2025-12-25", "2025-12-26"]


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")

    # backup
    bkp = DB_PATH.with_suffix(DB_PATH.suffix + f".bak_daily_equity_{int(time.time())}")
    shutil.copyfile(DB_PATH, bkp)
    print(f"[backup] {DB_PATH} -> {bkp}")

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")

        # show before
        for d in DATES_TO_DELETE:
            cur.execute("SELECT date, equity FROM daily_equity WHERE date = ?", (d,))
            row = cur.fetchone()
            if row:
                print(f"[before] {row[0]} equity={float(row[1]):.2f}")
            else:
                print(f"[before] {d} not found")

        # delete
        cur.executemany("DELETE FROM daily_equity WHERE date = ?", [(d,) for d in DATES_TO_DELETE])
        conn.commit()

        # show after
        for d in DATES_TO_DELETE:
            cur.execute("SELECT 1 FROM daily_equity WHERE date = ?", (d,))
            exists = cur.fetchone() is not None
            print(f"[after] {d} exists={exists}")

    finally:
        conn.close()

    print("\n[next] Now re-run daily task to re-generate the snapshot(s):")
    print("  python -m src.daily_once")


if __name__ == "__main__":
    main()

