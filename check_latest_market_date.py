import sqlite3
from pathlib import Path
import pandas as pd

DB = Path("data/etf_data.db")

# You can edit this list if you want to check more/less ETFs.
ETFS = [
    "510050",
    "159915",
    "510300",
    "510880",
    "512040",
    "513500",
]


def latest_date(etf: str) -> str | None:
    conn = sqlite3.connect(DB)
    try:
        try:
            df = pd.read_sql_query(f"SELECT 日期 FROM etf_{etf} ORDER BY 日期 DESC LIMIT 1", conn)
            if not df.empty:
                return str(df.iloc[0]["日期"])
        except Exception:
            df = pd.read_sql_query(f"SELECT date FROM etf_{etf} ORDER BY date DESC LIMIT 1", conn)
            if not df.empty:
                return str(df.iloc[0]["date"])
        return None
    finally:
        conn.close()


def main() -> None:
    if not DB.exists():
        raise FileNotFoundError(f"etf_data.db not found: {DB}")

    print(f"db: {DB.resolve()}")
    for e in ETFS:
        d = latest_date(e)
        print(f"{e}: {d}")


if __name__ == "__main__":
    main()

