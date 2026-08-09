# Knowledge Backup Runbook (K6)

Simple personal-project backup/export guide.

## What is protected

Canonical Knowledge lives in SQLite (`HERMES_KNOWLEDGE_DB_PATH` or default
`hermes-knowledge/knowledge.sqlite`). Backup/export produces secondary
artifacts only; SQLite remains the source of truth.

## Backup formats

| Format | Purpose | Notes |
|--------|---------|-------|
| SQLite copy (`.sqlite`) | Full point-in-time DB backup | Restore = replace DB file |
| JSON export (`.json`) | Structured, portable, verifiable | Lessons, sources, evidence, conflicts, lineage |
| Markdown export (`.md`) | Human-readable summary | Current approved lessons only |

## Integrity metadata

Every JSON export includes:
- `export_timestamp`
- `schema_version`
- `record_counts`
- `content_hash` (SHA-256 over the payload, excluding metadata)

Restore verifies the hash before importing. A tampered file is rejected.

## Commands (MCP tools)

- `knowledge_backup_db(owner_user_id, output_dir)` → SQLite copy
- `knowledge_export_json(owner_user_id, output_dir)` → structured JSON
- `knowledge_export_markdown(owner_user_id, output_dir)` → readable Markdown
- `knowledge_restore_verify_json(owner_user_id, input_path, target_db_path, new_owner_user_id="")`
  → restore into a temporary DB + parity check

## Hermes native cron

Weekly backup is enough for a personal project:

```bash
hermes cron create "0 8 * * 1" \
  "Run knowledge backup: create a SQLite DB copy and a structured JSON export into the configured backup directory, then report the artifact paths." \
  --name "k6-knowledge-backup" \
  --skill knowledge-learning \
  --deliver local
```

Optional monthly JSON export:

```bash
hermes cron create "0 8 1 * *" \
  "Export knowledge as structured JSON into the configured backup directory and report the path." \
  --name "k6-knowledge-export-monthly" \
  --skill knowledge-learning \
  --deliver local
```

Do not use high-frequency schedules.

## Restore (to a temporary DB)

```python
from pathlib import Path
from hermes.application.knowledge_export import KnowledgeRestoreService

service = KnowledgeRestoreService(Path("/tmp/restored.sqlite"))
result = service.restore_from_json("owner_id", Path("/path/to/export.json"))
print(result["restored_counts"])
```

`new_owner_user_id` remaps all restored lessons/sources to a new owner.
Original data is never overwritten during restore tests.

## Lessons without a title

If a lesson has no usable title, the Markdown export notes it as
`(untitled lesson)` and includes the source URL when present, so it can be
re-analyzed later. Nothing is dropped.

## What K6 does NOT do

- Does NOT make backup/export another source of truth
- Does NOT overwrite real user knowledge
- Does NOT auto-restore into the live DB
- Does NOT add a vector DB
- Does NOT add a new agent
