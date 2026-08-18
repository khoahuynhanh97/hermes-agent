"""
Proper migration: apply schema_v4 + schema_v5 from hermes codebase.
Idempotent: safe to re-run.
"""
import sqlite3
from pathlib import Path

DB_PATH = "D:/HermesData/hermes.db"

REQUIRED_TABLES = [
    'affiliate_products',
    'affiliate_research_runs',
    'affiliate_product_snapshots',
    'affiliate_references',
    'affiliate_content_ideas',
    'affiliate_content_packages',
    'affiliate_approval_events',
    'affiliate_run_products',
    'affiliate_projection_outbox',
    'affiliate_research_briefs',
    'affiliate_projection_items',
    'affiliate_jobs',
    'affiliate_stats',
]

print("=== Apply full Affiliate schema (v4 + v5) ===\n")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("PRAGMA user_version")
before = cursor.fetchone()[0]
print(f"Schema version before: {before}")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'affiliate%'")
existing_tables = [r[0] for r in cursor.fetchall()]
missing = set(REQUIRED_TABLES) - set(existing_tables)

print(f"Existing affiliate tables: {len(existing_tables)}/{len(REQUIRED_TABLES)}")
if missing:
    print(f"Missing: {sorted(missing)}")

if not missing and before >= 5:
    print(f"[SKIP] All {len(REQUIRED_TABLES)} tables already present")
    conn.close()
    exit(0)

print("\n[1/3] Apply schema_v4 (affiliate_run_products, projection_outbox, briefs)...")
try:
    from hermes.adapters.sqlite.schema_v4 import apply_schema_v4
    apply_schema_v4(conn)
    cursor.execute("PRAGMA user_version = 4")
    conn.commit()
    print("[OK] schema_v4 applied")
except Exception as e:
    print(f"[WARN] schema_v4 partial: {e}")
    conn.commit()

print("\n[2/3] Apply schema_v5 (projection_items, columns, backfills)...")
try:
    from hermes.adapters.sqlite.schema_v5 import apply_schema_v5
    apply_schema_v5(conn)
    cursor.execute("PRAGMA user_version = 5")
    conn.commit()
    print("[OK] schema_v5 applied")
except Exception as e:
    print(f"[WARN] schema_v5 partial: {e}")
    conn.commit()

print("\n[3/3] Verify all affiliate tables...")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'affiliate%' ORDER BY name")
existing_tables = [r[0] for r in cursor.fetchall()]
print(f"  Existing affiliate tables: {len(existing_tables)}")

missing = set(REQUIRED_TABLES) - set(existing_tables)
if missing:
    print(f"  [WARN] Still missing: {sorted(missing)}")
else:
    print(f"  [OK] All {len(REQUIRED_TABLES)} affiliate tables present")

for t in sorted(REQUIRED_TABLES):
    if t in existing_tables:
        cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
        count = cursor.fetchone()[0]
        print(f"    {t}: {count} rows")

cursor.execute("PRAGMA user_version")
after = cursor.fetchone()[0]
print(f"\nSchema version: V{before} -> V{after}")
conn.close()

print("\n=== Migration COMPLETE ===")

