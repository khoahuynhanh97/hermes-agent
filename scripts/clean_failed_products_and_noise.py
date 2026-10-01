import os
import shutil
import sqlite3

# 1. Clean D:\work\VideoAI
video_ai_dir = r"D:\work\VideoAI"
keep_folders = {"[Xiaomi] Desk Lamp Lite", "[TRIBIT] XSound Go Bluetooth Speaker"}
if os.path.exists(video_ai_dir):
    for item in os.listdir(video_ai_dir):
        if item not in keep_folders:
            path = os.path.join(video_ai_dir, item)
            print(f"Deleting test folder from VideoAI: {item}")
            if os.path.isdir(path) or os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)

# 2. Clean Product Intelligence daily_runs
pi_runs = r"D:\work\Personal\Product-Intelligence\data\daily_runs"
pi_bad_dates = ["2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"]
if os.path.exists(pi_runs):
    for d in pi_bad_dates:
        dp = os.path.join(pi_runs, d)
        if os.path.exists(dp):
            print(f"Deleting bad/noisy daily run: {d}")
            shutil.rmtree(dp, ignore_errors=True)

# 3. Clean Exchange inbox
inbox_dir = r"D:\work\Personal\hermes-product-video-exchange\inbox"
if os.path.exists(inbox_dir):
    for d in pi_bad_dates:
        dp = os.path.join(inbox_dir, d)
        if os.path.exists(dp):
            print(f"Deleting bad inbox date: {d}")
            shutil.rmtree(dp, ignore_errors=True)

    inbox_29 = os.path.join(inbox_dir, "2026-09-29")
    if os.path.exists(inbox_29):
        keep_runs = {"run_20260930_040252"}
        for item in os.listdir(inbox_29):
            if item not in keep_runs:
                path = os.path.join(inbox_29, item)
                print(f"Deleting stale test run in 2026-09-29 inbox: {item}")
                shutil.rmtree(path, ignore_errors=True)

# 4. Clean SQLite Database
db_path = r"C:\Users\ninak\AppData\Local\hermes\hermes.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Prune rejected promotional noise from master catalog
    cur.execute("DELETE FROM product_master_catalog WHERE canonical_product_key IN ('xiaomi:sale-40', 'jbl:top-12')")
    print(f"Deleted {cur.rowcount} rejected noise items from product_master_catalog")
    
    # Prune noise imports
    cur.execute("DELETE FROM daily_product_video_import WHERE canonical_product_key IN ('xiaomi:sale-40', 'jbl:top-12', 'oral-b:series-9') OR source_date IN ('2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25')")
    print(f"Deleted {cur.rowcount} noise import records from daily_product_video_import")
    
    # Prune failed test QC report
    cur.execute("DELETE FROM product_video_qc_reports WHERE workflow_id IN ('pv-daily-be6eac6be72f9bea', 'pv-daily-11f0dd9b3a81b2f9', 'pv-daily-dc9279efd5a70e44', 'pv-daily-d82c4e5c9c269af1')")
    print(f"Deleted {cur.rowcount} test QC reports")
    
    # Prune dummy workflow records
    cur.execute("DELETE FROM workflow WHERE workflow_id IN ('pv-daily-11f0dd9b3a81b2f9', 'pv-daily-dc9279efd5a70e44', 'pv-daily-d82c4e5c9c269af1', 'pv-daily-4ad6d7c17d2ec056')")
    print(f"Deleted {cur.rowcount} dummy workflows")
    
    conn.commit()
    conn.close()

print("Cleanup completed successfully.")
