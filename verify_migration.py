"""
Verify schema migration integrity.
- Check all old tables still have data
- Check new tables created correctly
- Check row counts match pre-migration
"""
import sqlite3
from pathlib import Path

DB_PATH = "D:/HermesData/hermes.db"

EXPECTED_PRE_COUNTS = {
    "lessons": 130,
    "sources": 54,
    "evidence": 110,
    "lesson_evidence": 110,
    "lesson_events": 215,
    "lesson_fts": 99,
    "messages": 18,
    "jobs": 47,
}

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("=== Verify Schema Integrity ===\n")

cursor.execute("PRAGMA user_version")
version = cursor.fetchone()[0]
print(f"Schema version: {version} (expected: 5)")

if version != 5:
    print(f"[ERROR] Schema version mismatch")
    conn.close()
    exit(1)

print("\n[1/3] Verify old table data preserved:")
all_ok = True
for table, expected_count in EXPECTED_PRE_COUNTS.items():
    cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
    actual_count = cursor.fetchone()[0]
    status = "OK" if actual_count == expected_count else "FAIL"
    if actual_count != expected_count:
        all_ok = False
    print(f"  [{status}] {table}: {actual_count} (expected {expected_count})")

if not all_ok:
    print("[ERROR] Some table counts don't match")
    conn.close()
    exit(1)

print("\n[2/3] Verify new affiliate tables:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'affiliate%' ORDER BY name")
affiliate_tables = [r[0] for r in cursor.fetchall()]
print(f"  Affiliate tables: {affiliate_tables}")

expected_affiliate = ["affiliate_jobs", "affiliate_products", "affiliate_stats"]
for table in expected_affiliate:
    if table not in affiliate_tables:
        print(f"[ERROR] Missing table: {table}")
        conn.close()
        exit(1)

for table in affiliate_tables:
    cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
    count = cursor.fetchone()[0]
    print(f"  [OK] {table}: {count} rows (empty, ready for data)")

print("\n[3/3] Verify indexes:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_affiliate%' ORDER BY name")
affiliate_indexes = [r[0] for r in cursor.fetchall()]
print(f"  Affiliate indexes: {affiliate_indexes}")
print(f"  Total indexes: {len(affiliate_indexes)} (expected: 8)")

if len(affiliate_indexes) < 8:
    print("[ERROR] Missing affiliate indexes")
    conn.close()
    exit(1)

cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='affiliate_products'")
idx_products = [r[0] for r in cursor.fetchall()]
print(f"\n  affiliate_products indexes: {idx_products}")

cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='affiliate_jobs'")
idx_jobs = [r[0] for r in cursor.fetchall()]
print(f"  affiliate_jobs indexes: {idx_jobs}")

cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='affiliate_stats'")
idx_stats = [r[0] for r in cursor.fetchall()]
print(f"  affiliate_stats indexes: {idx_stats}")

cursor.execute("PRAGMA integrity_check")
integrity = cursor.fetchone()[0]
print(f"\n[INTEGRITY] {integrity}")

if integrity != "ok":
    print("[ERROR] Database integrity check failed")
    conn.close()
    exit(1)

conn.close()
print("\n=== ALL CHECKS PASSED ===")
print("Database is ready for Affiliate testing.")
