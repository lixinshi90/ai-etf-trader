import sqlite3

conn = sqlite3.connect('data/trade_history.db')
cur = conn.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS daily_equity (date TEXT PRIMARY KEY, equity REAL)')
cur.execute('SELECT date, equity FROM daily_equity ORDER BY date DESC LIMIT 30')
rows = cur.fetchall()
conn.close()

for d, e in rows:
    print(d, float(e))

