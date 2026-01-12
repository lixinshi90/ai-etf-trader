$script = @'
import sqlite3, yaml
from pathlib import Path
db = Path(r"data/trade_history.db")
cfg = Path(r"config.yaml")
init = 100000.0
 try:
 with open(cfg, "r", encoding="utf-8") as f:
 init = float((yaml.safe_load(f) or {}).get("strategy", {}).get("initial_capital", init))
except Exception:
pass
conn = sqlite3.connect(str(db))
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)")
cur.execute("INSERT OR IGNORE INTO daily_equity(date, equity) VALUES (?, ?)", ("2025-11-26", init))
conn.commit()
conn.close()
print("seeded 2025-11-26 with equity", init)
