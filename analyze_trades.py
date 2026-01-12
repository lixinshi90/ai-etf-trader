import sqlite3
import pandas as pd

conn = sqlite3.connect('data/trade_history.db')
df = pd.read_sql_query('SELECT * FROM trades WHERE date >= "2025-12-11" ORDER BY date', conn)
print(df.to_string())
conn.close()


