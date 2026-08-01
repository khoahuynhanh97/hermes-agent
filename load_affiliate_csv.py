"""
Load affiliate CSV -> affiliate_products, create affiliate_jobs.
Tests full pipeline: CSV import -> DB -> job queue.
"""
import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = "D:/HermesData/hermes.db"
IMPORT_DIR = Path("D:/HermesData/affiliate_imports")

CSV_FILE = IMPORT_DIR / "sample_products_20260801.csv"

print("=== Load Affiliate CSV -> DB ===\n")

if not CSV_FILE.exists():
    print(f"[ERROR] CSV file not found: {CSV_FILE}")
    exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print(f"CSV file: {CSV_FILE}")
print(f"DB: {DB_PATH}\n")

now = datetime.now().isoformat()
products_loaded = 0
jobs_created = []

with open(CSV_FILE, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"Found {len(rows)} products in CSV")
print(f"\n[1/3] Importing products to affiliate_products...")

for row in rows:
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO affiliate_products (
                source, source_id, title, description, price, currency,
                url, image_url, category, tags, sku, affiliate_link,
                commission_rate, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row['source'],
            row['source_id'],
            row['title'],
            row['description'],
            float(row['price']) if row['price'] else None,
            row['currency'],
            row['url'],
            row['image_url'],
            row['category'],
            row['tags'],
            row['sku'],
            row['affiliate_link'],
            float(row['commission_rate']) if row['commission_rate'] else None,
            row['status'],
            now,
            now,
        ))

        if cursor.rowcount > 0:
            products_loaded += 1
            product_id = cursor.lastrowid
            jobs_created.append({
                'product_id': product_id,
                'title': row['title'],
                'source': row['source'],
            })
            print(f"  + {row['source_id']}: {row['title'][:50]}...")
    except Exception as e:
        print(f"  [ERROR] Failed to import {row.get('source_id', 'unknown')}: {e}")

conn.commit()
print(f"\n[OK] Loaded {products_loaded} new products")

print(f"\n[2/3] Creating affiliate_jobs for each product...")
for job in jobs_created:
    cursor.execute("""
        INSERT INTO affiliate_jobs (
            product_id, job_type, payload_json, status, attempts, max_attempts,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job['product_id'],
        'process_product',
        json.dumps({
            'source': job['source'],
            'action': 'fetch_metadata',
            'priority': 'normal',
        }),
        'pending',
        0,
        3,
        now,
        now,
    ))
    job['job_id'] = cursor.lastrowid
    print(f"  + Job #{job['job_id']} for {job['title'][:40]}")

conn.commit()
print(f"\n[OK] Created {len(jobs_created)} affiliate jobs")

print(f"\n[3/3] Final database state:")
cursor.execute("SELECT COUNT(*) FROM affiliate_products")
print(f"  affiliate_products: {cursor.fetchone()[0]} rows")

cursor.execute("SELECT COUNT(*) FROM affiliate_jobs")
print(f"  affiliate_jobs: {cursor.fetchone()[0]} rows")

cursor.execute("SELECT status, COUNT(*) FROM affiliate_jobs GROUP BY status")
for status, count in cursor.fetchall():
    print(f"    {status}: {count}")

print(f"\n=== Import SUCCESS ===")
print(f"Created {len(jobs_created)} jobs ready to process")

conn.close()
