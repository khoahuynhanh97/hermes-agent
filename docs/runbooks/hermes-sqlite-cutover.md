# Hermes SQLite Cutover

## Active Configuration

```dotenv
HERMES_STORAGE_BACKEND=sqlite
HERMES_DATA_DIR=D:\HermesData
HERMES_DB_PATH=D:\HermesData\hermes.db
HERMES_BACKUP_DIR=G:\My Drive\Hermes Knowledge Base\backups
LLM_PROVIDER=router
LLM_BASE_URL=http://127.0.0.1:20128/v1
LLM_ENABLE_LEGACY_PROVIDER_FALLBACK=0
```

Keep credentials and the Telegram owner ID only in `.env`. Do not commit them.

## Migration Procedure

1. Stop all Hermes bot and worker processes; leave local 9Router running.
2. Archive `unified_index.json` and `entries/` from the legacy knowledge directory.
3. Run the dry migration:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_knowledge_to_sqlite.py `
  --source-root "G:\My Drive\Hermes Knowledge Base\knowledge_base" `
  --database "D:\HermesData\hermes.db" `
  --owner-user-id <telegram-owner-id>
```

4. Compare total and per-status counts, then repeat with `--apply`.
5. Run `PRAGMA quick_check`, the Hermes unit tests, and the legacy regression scripts.
6. Set the active configuration above and start exactly one bot and one worker.
7. Create and verify the first Drive backup/export.

## Rollback

Stop Hermes, set `HERMES_STORAGE_BACKEND=json`, and restart only if immediate rollback is required. The legacy JSON is retained read-only. Once SQLite changes have accumulated, prefer restoring a verified SQLite backup instead of returning to JSON because JSON will no longer contain the latest lifecycle events.
