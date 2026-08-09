# Hermes SQLite Backup And Restore

Hermes uses `D:\HermesData\hermes.db` as the active database on laptop 1. Google Drive contains backup and export files only. Do not run the live database from a synced Drive folder.

## Create And Verify A Backup

```powershell
cd D:\work\hermes-agent
.\.venv\Scripts\python.exe scripts\hermes_backup.py backup
.\.venv\Scripts\python.exe scripts\hermes_backup.py verify "G:\My Drive\Hermes Knowledge Base\backups\hermes-<timestamp>.db"
```

`HERMES_BACKUP_DIR` controls the destination. The backup command uses SQLite's backup API and runs an integrity check before publishing the file. The default retention is 14 database backups.

## Export Readable Data

```powershell
.\.venv\Scripts\python.exe scripts\hermes_backup.py export
```

The JSON export includes sources, evidence, lesson lifecycle events, approved/pending/rejected lessons, memory, and jobs. It does not include API keys or Telegram tokens.

## Restore On Laptop 1

1. Stop `telegram_bot.py` and `scripts\run_job_worker.py`.
2. Verify the selected backup.
3. Restore with explicit confirmation:

```powershell
.\.venv\Scripts\python.exe scripts\hermes_backup.py restore "G:\My Drive\Hermes Knowledge Base\backups\hermes-<timestamp>.db" --confirm
```

Restore creates a `pre-restore` backup first, verifies the replacement, and removes stale WAL/SHM files. Start one bot and one worker after it succeeds.

## Passive Laptop 2

Laptop 2 must remain passive while laptop 1 is running. Copy or restore a verified Drive backup into a local path such as `D:\HermesData\hermes.db`, configure the same owner allowlist, and start the bot only after laptop 1 is stopped. Never run both laptops against one synced SQLite file.
