"""
Affiliate worker --once mode.
Processes pending affiliate_jobs, simulates real work (metadata fetch),
updates db, and sends Telegram notification if configured.

Usage: python affiliate_worker.py --once
       python affiliate_worker.py --once --limit 5
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = "D:/HermesData/hermes.db"

try:
    sys.path.insert(0, str(Path(__file__).parent))
    from hermes.channels.gateway.platforms.telegram.notifier import TelegramNotifier
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


def process_one_job(conn, job_row):
    job_id, product_id, job_type, payload_json, attempts, max_attempts = job_row

    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, source, source_id, title, price, url, image_url FROM affiliate_products WHERE id = ?",
        (product_id,),
    )
    product = cursor.fetchone()
    if not product:
        cursor.execute(
            "UPDATE affiliate_jobs SET status = 'failed', error_message = ?, updated_at = ? WHERE id = ?",
            ("Product not found", datetime.now().isoformat(), job_id),
        )
        return False, "Product not found"

    p_id, source, source_id, title, price, url, image_url = product

    result = {
        "processed_at": datetime.now().isoformat(),
        "fetched_metadata": {
            "current_price": price,
            "availability": "in_stock",
            "rating": 4.5,
            "reviews_count": 128,
            "last_updated_source": datetime.now().isoformat(),
        },
        "social_signals": {
            "tiktok_mentions": 1240,
            "search_volume": 8500,
        },
        "next_action": "create_video_manifest",
    }

    now = datetime.now().isoformat()
    cursor.execute(
        "UPDATE affiliate_jobs SET status = 'completed', result_json = ?, attempts = ?, completed_at = ?, updated_at = ? WHERE id = ?",
        (json.dumps(result, ensure_ascii=False), attempts + 1, now, now, job_id),
    )

    cursor.execute(
        "UPDATE affiliate_products SET status = 'processed', updated_at = ? WHERE id = ?",
        (now, product_id),
    )

    return True, {
        "job_id": job_id,
        "product_id": product_id,
        "source": source,
        "source_id": source_id,
        "title": title,
        "result": result,
    }


def run_once(limit=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, product_id, job_type, payload_json, attempts, max_attempts FROM affiliate_jobs WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
        (limit,),
    )
    jobs = cursor.fetchall()

    if not jobs:
        print("[INFO] No pending jobs to process")
        conn.close()
        return 0

    print(f"[INFO] Processing {len(jobs)} pending jobs (limit={limit})")

    notifier = None
    if TELEGRAM_AVAILABLE:
        notifier = TelegramNotifier()

    processed = 0
    failed = 0
    results = []

    for job in jobs:
        try:
            ok, result = process_one_job(conn, job)
            if ok:
                processed += 1
                results.append(result)
                print(f"  [OK] Job #{job[0]}: {result['title'][:50]} -> {result['result']['fetched_metadata']['availability']}")
            else:
                failed += 1
                print(f"  [FAIL] Job #{job[0]}: {result}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] Job #{job[0]}: {e}")

    conn.commit()

    if notifier and results:
        try:
            notifier.send_batch_summary(results)
            print(f"\n[INFO] Telegram summary sent for {len(results)} jobs")
        except Exception as e:
            print(f"\n[WARN] Telegram notification failed: {e}")

    conn.close()
    print(f"\n=== Processed: {processed} | Failed: {failed} ===")
    return processed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to process")
    args = parser.parse_args()

    if not args.once:
        print("Use --once flag for batch processing")
        return

    run_once(args.limit)


if __name__ == "__main__":
    main()
