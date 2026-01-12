import sqlite3
conn = sqlite3.connect(r"data/trade_history.db")
cur = conn.cursor()
cur.execute("UPDATE daily_equity SET equity=? WHERE date=?", (99962.97, "2025-12-17"))
conn.commit()
conn.close()
print("updated 2025-12-17 to 99962.97")
