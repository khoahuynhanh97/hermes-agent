import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, 'D:/work/hermes-agent')
from hermes.db import SCHEMA_V1, SCHEMA_VERSION

print(f"SCHEMA_VERSION constant: {SCHEMA_VERSION}")
print(f"SCHEMA_V1 length: {len(SCHEMA_V1)}")

# Find affiliate tables in SCHEMA_V1
affiliate_tables_in_v1 = []
for line in SCHEMA_V1.split('\n'):
    if 'CREATE TABLE' in line and 'affiliate' in line.lower():
        affiliate_tables_in_v1.append(line.strip())

print(f"\nAffiliate tables in SCHEMA_V1: {len(affiliate_tables_in_v1)}")
for t in affiliate_tables_in_v1:
    print(f"  {t}")

# Now try executing SCHEMA_V1 directly
conn = sqlite3.connect('D:/HermesData/hermes.db')
cursor = conn.cursor()

print("\nExecuting SCHEMA_V1 directly...")
try:
    cursor.executescript(SCHEMA_V1)
    conn.commit()
    print("[OK] SCHEMA_V1 executed directly")
except Exception as e:
    print(f"[ERROR] {e}")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'affiliate%' ORDER BY name")
print("\nAffiliate tables after direct execution:")
for r in cursor.fetchall():
    print(f"  {r[0]}")

conn.close()
