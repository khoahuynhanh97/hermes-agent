# Crawl4AI Runtime Readiness Report

**Date:** 2026-08-02
**Status:** BLOCKED_WAITING_FOR_APPROVED_URLS — runtime installed, DB migrated, pilot not run

---

## Branch & Commit

- Branch: `codex/hermes-personal-assistant-core`
- HEAD: `83f0c8b55` (`style: clean Crawl4AI integration whitespace`)
- Working tree: user dirty files preserved (see "Dirty Files" section). No files overwritten.

## Runtime Versions

| Component | Version |
| :--- | :--- |
| Crawl4AI | `0.9.2` (pinned via `requirements-crawl4ai.txt`) |
| Playwright | `1.62.0` |
| Chromium | `151.0.7922.34` |
| Python (venv) | `3.12.13` |

## crawl4ai-doctor Result

- `crawl4ai-doctor` PASSED. Browser launched headless, fetched, scraped, exported media, "Crawling test passed!".

## Offline Test Gate

Command run (15 files, `--basetemp .pytest-crawl4ai-runtime-verification`):

```text
63 passed in 9.52s
```

- 63/63 PASS, 0 network calls, 0 browser launches, no paid provider calls.
- Test files: test_web_document, test_web_url_policy, test_static_fetcher, test_crawl4ai_fetcher, test_web_document_normalizer, test_web_acquisition_service, test_web_research_config, test_web_document_repository, test_affiliate_web_reference_service, test_crawl4ai_recovery, test_crawl4ai_affiliate_acceptance, test_affiliate_research_acceptance, test_affiliate_final_review, test_database.

## Database Migration

### Important deviation from plan (must be disclosed)

- Preflight verified production DB at schema **V5** (`PRAGMA user_version = 5`), no `web_documents` table.
- A **process supervisor owned by the Antigravity IDE** (`language_server.exe`, PID 17320) auto-restarts `telegram_bot.py` and `scripts/run_job_worker.py` whenever they are stopped. Stopping the workers/bots during backup caused the supervisor to restart them ~40s later; the restarted worker called `Database.initialize()`, which migrated the DB to **V6 automatically** before a clean V5 backup could be taken.
- Consequence: the timestamped backup created after that event (`hermes_V6_snapshot_20260802_000121.db`) is a **V6** snapshot, not V5. File was renamed to reflect the truth. The migration itself is safe (see below).

### Migration safety verification

- V6 migration (`schema_v6.py`) is **additive only**: creates `web_documents` and `affiliate_run_web_documents`, plus indexes. It does not alter any V2/V5 table.
- Post-migration `PRAGMA user_version = 6`.
- Tables `web_documents` and `affiliate_run_web_documents` exist (both empty, 0 rows — expected, no web acquisition has run yet).
- Pre-existing V2-era data intact:
  - Before: 130 lessons, 54 sources, 110 evidence, 47 jobs (from `hermes_V2_backup_20260801_172911.db`).
  - After: 136 lessons, 56 sources, 116 evidence, 57 jobs (delta = legitimate new data from the earlier affiliate run).
  - Affiliate data intact: 150 products, 150 snapshots, 6 runs, 750 run_products, 11 briefs, 33 ideas, 8 packages, 10 affiliate_jobs, 6 outbox, 8 projection items.

### Foreign key check

- `PRAGMA foreign_key_check` reports 10 violations, all in `affiliate_jobs` referencing `affiliate_products` (rowid 0 = product rows that no longer exist). This is a **pre-existing data condition from earlier affiliate migration work, not caused by V6**. Not blocking V6 operations, but it is a **legacy data issue requiring a separate maintenance pass** (delete or re-link the 10 orphaned `affiliate_jobs` rows) before production affiliate flows rely on strict FK integrity.

## Backups (paths redacted)

| Backup | SHA-256 | user_version | Integrity |
| :--- | :--- | :--- | :--- |
| `D:\HermesData\backups\hermes_V2_backup_20260801_172911.db` | (pre-existing) | 2 | ok |
| `D:\HermesData\backups\hermes_V6_snapshot_20260802_000121.db` | `93d7cafb069c5343c7b740fdfb1bf47977f4dd5b8408e685bbdf37fcae8d9ed1` | 6 | ok |
| `D:\HermesData\backups\hermes_V6_snapshot_20260802_000550.db` | `93d7cafb069c5343c7b740fdfb1bf47977f4dd5b8408e685bbdf37fcae8d9ed1` | 6 | ok |

- **Both `hermes_V6_snapshot_*` backups are schema V6.** There is **no V5 backup** (the pre-migration V5 snapshot could not be taken because the Antigravity supervisor restarted the worker, which ran `Database.initialize()` and migrated V5→V6 before the V5 backup was captured).
- The two V6 snapshots have identical SHA-256 (taken seconds apart, no writes between) — cross-validates backup integrity.
- Backups verified openable read-only; `PRAGMA integrity_check = ok`.
- Location: `D:\HermesData\backups\` (outside the git repository).
- **Rollback caveat:** restoring the V2 backup (`hermes_V2_backup_20260801_172911.db`) will **lose all data created after 2026-08-01 17:29** — the affiliate V3→V6 migration data, the 150 imported products, 8 content packages, and all runs/briefs. Restoring a V6 snapshot preserves current state and loses only post-backup writes.

## Pilot

### Pilot input template

- File: `scratch\crawl4ai-pilot-urls.json` — **created as template only**.
- Contains a single placeholder entry (`https://public-example.com/article`) demonstrating the expected schema:
  `url`, `external_product_id`, `source_kind`.
- Allowed `source_kind`: `manufacturer`, `editorial_review`, `documentation`, `public_article`.
- The pilot tool validates: 10–20 entries, max 5 URLs per host, no duplicate URLs, `source_kind` allowlist, and `PublicWebUrlPolicy` on every URL. Invalid input fails fast with an error.
- **No real URLs were selected or crawled.** This step requires user-supplied approval of 10–20 public HTTP/HTTPS URLs.

### Pilot execution

- NOT RUN. Blocked on approved URL list.

## Readiness Criteria — Pass/Fail

| Criterion | Status |
| :--- | :--- |
| 100% URLs from approved list | ⛔ BLOCKED — no approved URL list |
| No SSRF/security-policy bypass | ✅ code-level (tests), ⛔ not proven on live pilot |
| No browser crash | ⛔ not exercised (no pilot) |
| No secrets in logs/reports | ✅ |
| Dynamic pages materially better than static | ⛔ not measured (no pilot) |
| Offline tests pass after pilot | ⛔ pilot not run |
| Database V6 works | ✅ |
| Recovery/idempotency (no re-fetch) | ✅ code-level (tests), ⛔ not proven live |

## CRAWL4AI_ENABLED

- Current value: **0** (not set in `.env`; `hermes/web_research_config.py` defaults to `"0"`).
- Remains `0` until ALL pilot criteria pass. No change was made to any environment or git-tracked secret file.

## Errors & Residual Risks

1. **Migration ran before V5 backup (disclosed above).** V5-specific backup does not exist; the earliest recoverable snapshot is `hermes_V2_backup_20260801_172911.db` (V2). Recovery to V2 loses all affiliate data created after 2026-08-01 17:29; recovery to the latest V6 snapshot keeps current data and loses only post-backup writes.
2. **Process supervisor auto-restarts workers/bots.** Any future backup/migration that needs the DB quiescent must either stop the Antigravity supervisor (`language_server.exe`) or accept that `Database.initialize()` may run concurrently. This is an environment fact, not a code bug.
3. **10 FK violations in `affiliate_jobs`** (pre-existing, refer to deleted `affiliate_products` rows). Does not block V6 operations; requires a separate data-maintenance pass before strict FK integrity is relied on.
4. **Crawl4AI pulls 86 optional packages** (LiteLLM, scipy, nltk, shapely, trimesh, patchright, etc.) into the venv. Isolated from base `requirements.txt`; only affects the optional runtime.

## Rollback

1. Stop workers/bots (note: supervisor may restart them).
2. Restore a backup over `D:\HermesData\hermes.db`:
   - `hermes_V6_snapshot_20260802_000550.db` — preferred; keeps web-document capability and current data.
   - `hermes_V2_backup_20260801_172911.db` — only if returning to pre-affiliate state is required; **loses all data created after 2026-08-01 17:29**.
3. Verify `PRAGMA user_version` and `integrity_check`.
4. Restart bot + worker.

## Dirty Files Confirmation

- Pre-existing uncommitted changes in the repo were NOT modified or staged:
  `.env.example`, `.gitignore`, `config.py`, `core/agent_jobs.py`, `core/job_watcher.py`, `core/video_fetcher.py`, `gui/*`, `hermes/adapters/sqlite/project_repository.py`, `hermes/adapters/sqlite/schema_v2.py`, `hermes/ports/project_repository.py`, `requirements.txt`, `tools/*`, `web/src/app.tsx`, `web_studio.py`, plus untracked files (docs, scripts, tests, etc.).
- No protected files were edited: `.env.example`, `config.py`, `requirements.txt`, `core/job_watcher.py` unchanged by this work.
- No secrets printed in this report.

## Next Action

- **Operator must supply 10–20 approved public HTTP/HTTPS URLs** in `scratch\crawl4ai-pilot-urls.json` (valid `source_kind`, no shopee/tiktok/youtube/facebook/instagram, no login, no media).
- Then run:
  `powershell .\.venv\Scripts\python.exe scripts\crawl4ai_pilot.py --input .\scratch\crawl4ai-pilot-urls.json --output .\scratch\crawl4ai-pilot-report.json`
- Only after all criteria pass, set `CRAWL4AI_ENABLED=1` (host environment, not git-tracked files).
