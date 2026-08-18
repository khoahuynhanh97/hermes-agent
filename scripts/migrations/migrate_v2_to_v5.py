"""
Migration V2 -> V5: Add Affiliate tables for product import/processing.

New tables:
- affiliate_products: Raw imported products from CSV/Sheets
- affiliate_jobs: Job tracking for affiliate processing
- affiliate_stats: Statistics/analytics per product

Safe to run multiple times (idempotent).
"""
import sqlite3
from pathlib import Path

DB_PATH = "D:/HermesData/hermes.db"

AFFILIATE_PRODUCTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS affiliate_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price REAL,
    currency TEXT DEFAULT 'VND',
    url TEXT,
    image_url TEXT,
    category TEXT,
    tags TEXT,
    sku TEXT,
    affiliate_link TEXT,
    commission_rate REAL,
    metadata_json TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source, source_id)
);
"""

AFFILIATE_JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS affiliate_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    job_type TEXT NOT NULL,
    payload_json TEXT,
    status TEXT DEFAULT 'pending',
    result_json TEXT,
    error_message TEXT,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (product_id) REFERENCES affiliate_products(id) ON DELETE CASCADE
);
"""

AFFILIATE_STATS_SCHEMA = """
CREATE TABLE IF NOT EXISTS affiliate_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    views INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    conversions INTEGER DEFAULT 0,
    revenue REAL DEFAULT 0,
    date TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES affiliate_products(id) ON DELETE CASCADE,
    UNIQUE(product_id, date)
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_affiliate_products_status ON affiliate_products(status)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_products_category ON affiliate_products(category)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_products_source ON affiliate_products(source)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_jobs_status ON affiliate_jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_jobs_product ON affiliate_jobs(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_jobs_type ON affiliate_jobs(job_type)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_stats_product ON affiliate_stats(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_affiliate_stats_date ON affiliate_stats(date)",
]

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("=== Migration V2 -> V5 ===")
print(f"Database: {DB_PATH}")

cursor.execute("PRAGMA user_version")
current_version = cursor.fetchone()[0]
print(f"Current version: {current_version}")

if current_version >= 5:
    print(f"[SKIP] Already at version {current_version}")
    conn.close()
    exit(0)

print("\n[1/4] Creating affiliate_products table...")
cursor.execute(AFFILIATE_PRODUCTS_SCHEMA)
print("[OK] affiliate_products created")

print("\n[2/4] Creating affiliate_jobs table...")
cursor.execute(AFFILIATE_JOBS_SCHEMA)
print("[OK] affiliate_jobs created")

print("\n[3/4] Creating affiliate_stats table...")
cursor.execute(AFFILIATE_STATS_SCHEMA)
print("[OK] affiliate_stats created")

print("\n[4/4] Creating indexes...")
for idx_sql in INDEXES:
    cursor.execute(idx_sql)
print(f"[OK] {len(INDEXES)} indexes created")

cursor.execute("PRAGMA user_version = 5")
conn.commit()

cursor.execute("PRAGMA user_version")
new_version = cursor.fetchone()[0]
print(f"\n[OK] Migration complete: V{current_version} -> V{new_version}")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'affiliate%' ORDER BY name")
affiliate_tables = [r[0] for r in cursor.fetchall()]
print(f"Affiliate tables: {affiliate_tables}")

conn.close()
print("\n=== Migration SUCCESS ===")
