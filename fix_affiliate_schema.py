"""
Fix affiliate_products schema: drop wrong test table, recreate with correct schema_v3.

All dependent tables are empty (test data only), so safe to drop & recreate.
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = "D:/HermesData/hermes.db"

print("=== Fix affiliate_products schema ===\n")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = OFF")

# Verify current wrong schema
cursor.execute("PRAGMA table_info(affiliate_products)")
current_cols = [r[1] for r in cursor.fetchall()]
print(f"Current columns: {len(current_cols)} -> {current_cols[:5]}...")

# Verify dependent tables are empty (safe to drop)
for table in ['affiliate_products', 'affiliate_run_products', 'affiliate_research_briefs',
              'affiliate_product_snapshots', 'affiliate_references',
              'affiliate_content_ideas', 'affiliate_content_packages',
              'affiliate_approval_events', 'affiliate_projection_items']:
    try:
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        count = cursor.fetchone()[0]
        print(f"  {table}: {count} rows")
        if count > 0 and table != 'affiliate_products':
            print(f"  [WARN] {table} not empty, aborting")
            conn.close()
            sys.exit(1)
    except sqlite3.OperationalError:
        pass

# Drop the wrong affiliate_products + dependent empty tables
print("\nDropping wrong affiliate_products and dependent empty tables...")
tables_to_drop = [
    'affiliate_products',
    'affiliate_approval_events',
    'affiliate_content_ideas',
    'affiliate_content_packages',
    'affiliate_product_snapshots',
    'affiliate_references',
    'affiliate_run_products',
    'affiliate_research_briefs',
    'affiliate_projection_items',
]
for table in tables_to_drop:
    try:
        cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
        print(f"  Dropped {table}")
    except sqlite3.OperationalError as e:
        print(f"  [WARN] Could not drop {table}: {e}")

conn.commit()
conn.close()

# Re-run initialize to recreate correct schema
print("\nRe-running Database.initialize()...")
sys.path.insert(0, 'D:/work/hermes-agent')
from hermes.db import Database
database = Database(DB_PATH)

# Force re-apply by resetting version to 2, then initialize applies 3,4,5
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("PRAGMA user_version = 2")
conn.commit()
conn.close()

database.initialize()
print("[OK] initialize() completed")

# Verify correct schema
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(affiliate_products)")
new_cols = [r[1] for r in cursor.fetchall()]
print(f"\nNew affiliate_products columns: {len(new_cols)}")
print(new_cols)

required = ['id', 'owner_user_id', 'platform', 'external_product_id', 'name',
            'category', 'price_vnd', 'source_type', 'source_url',
            'authorization_scope', 'rights_status', 'content_hash']
missing = [c for c in required if c not in new_cols]
if missing:
    print(f"[ERROR] Still missing: {missing}")
else:
    print(f"[OK] Correct schema_v3 affiliate_products present")

cursor.execute("PRAGMA user_version")
print(f"Schema version: {cursor.fetchone()[0]}")
conn.close()
print("\n=== FIX COMPLETE ===")
