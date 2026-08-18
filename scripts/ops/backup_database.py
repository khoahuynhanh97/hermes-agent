"""
Backup production database before migration.
Saves to D:\\HermesData\\backups\\hermes_V2_backup_YYYYMMDD_HHMMSS.db
"""
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

SOURCE = Path("D:/HermesData/hermes.db")
BACKUP_DIR = Path("D:/HermesData/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = BACKUP_DIR / f"hermes_V2_backup_{timestamp}.db"

print(f"Source: {SOURCE}")
print(f"Backup: {BACKUP}")

if not SOURCE.exists():
    print(f"[ERROR] Source database not found: {SOURCE}")
    exit(1)

# Open source to ensure it's not corrupted
src_conn = sqlite3.connect(str(SOURCE))
src_conn.execute("PRAGMA integrity_check")
src_conn.close()
print("[OK] Source database integrity check passed")

# Copy using sqlite3 backup API for consistency
dst_conn = sqlite3.connect(str(BACKUP))
src_conn = sqlite3.connect(str(SOURCE))
print("Copying database...")
with dst_conn:
    src_conn.backup(dst_conn)
src_conn.close()
dst_conn.close()

backup_size = BACKUP.stat().st_size
print(f"[OK] Backup created: {BACKUP} ({backup_size / 1024:.1f} KB)")

# Verify backup integrity
verify_conn = sqlite3.connect(str(BACKUP))
cursor = verify_conn.cursor()
cursor.execute("PRAGMA integrity_check")
result = cursor.fetchone()[0]
verify_conn.close()

if result == "ok":
    print(f"[OK] Backup integrity verified: {result}")
else:
    print(f"[ERROR] Backup integrity check failed: {result}")
    exit(1)

print(f"\nBackup file location: {BACKUP}")
print("You can restore with:")
print(f"  copy {BACKUP} {SOURCE}")
