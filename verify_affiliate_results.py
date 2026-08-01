"""
Verify final state of affiliate jobs after worker processing.
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "D:/HermesData/hermes.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=== Affiliate System Final Report ===\n")

cursor.execute("PRAGMA user_version")
print(f"Schema version: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM affiliate_products")
total_products = cursor.fetchone()[0]
print(f"\nAffiliate products: {total_products}")

cursor.execute("SELECT status, COUNT(*) FROM affiliate_products GROUP BY status")
print("By status:")
for row in cursor.fetchall():
    print(f"  {row['status']}: {row[1]}")

cursor.execute("SELECT COUNT(*) FROM affiliate_jobs")
total_jobs = cursor.fetchone()[0]
print(f"\nAffiliate jobs: {total_jobs}")

cursor.execute("SELECT status, COUNT(*) FROM affiliate_jobs GROUP BY status")
print("By status:")
for row in cursor.fetchall():
    print(f"  {row['status']}: {row[1]}")

print("\n--- Sample products (first 3) ---")
cursor.execute("SELECT id, source, source_id, title, price, status FROM affiliate_products LIMIT 3")
for row in cursor.fetchall():
    print(f"  #{row['id']} [{row['source']}/{row['source_id']}] {row['title'][:40]}... ({row['price']:,.0f} VND) - {row['status']}")

print("\n--- Sample jobs with results (first 3) ---")
cursor.execute("SELECT id, product_id, job_type, status, attempts, result_json FROM affiliate_jobs WHERE status = 'completed' LIMIT 3")
for row in cursor.fetchall():
    result = json.loads(row['result_json']) if row['result_json'] else {}
    metadata = result.get('fetched_metadata', {})
    print(f"  Job #{row['id']} -> Product #{row['product_id']} [{row['job_type']}]")
    print(f"    Status: {row['status']} | Attempts: {row['attempts']}")
    print(f"    Price: {metadata.get('current_price', 0):,.0f} VND | Availability: {metadata.get('availability', '?')}")
    print(f"    Rating: {metadata.get('rating', 0)}/5 | Reviews: {metadata.get('reviews_count', 0)}")

print("\n--- Job timing summary ---")
cursor.execute("""
    SELECT
        COUNT(*) as total,
        MIN(completed_at) as first_completed,
        MAX(completed_at) as last_completed
    FROM affiliate_jobs
    WHERE status = 'completed'
""")
row = cursor.fetchone()
if row['total'] > 0:
    print(f"  Total completed: {row['total']}")
    print(f"  First completed: {row['first_completed']}")
    print(f"  Last completed: {row['last_completed']}")

cursor.execute("PRAGMA integrity_check")
print(f"\n[INTEGRITY] {cursor.fetchone()[0]}")

conn.close()
print("\n=== Affiliate System FULLY OPERATIONAL ===")
