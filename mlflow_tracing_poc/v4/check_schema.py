"""Check database schema."""
import sqlite3

conn = sqlite3.connect('mlflow_v4.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

# Check trace_info table
if ('trace_info',) in tables:
    cursor.execute("PRAGMA table_info(trace_info)")
    cols = cursor.fetchall()
    print("\ntrace_info columns:", [c[1] for c in cols])

# Check spans table
if ('spans',) in tables:
    cursor.execute("PRAGMA table_info(spans)")
    cols = cursor.fetchall()
    print("\nspans columns:", [c[1] for c in cols])
    
    cursor.execute("SELECT * FROM spans LIMIT 5")
    rows = cursor.fetchall()
    print("\nSample spans:")
    for r in rows:
        print(f"  {r}")

conn.close()
