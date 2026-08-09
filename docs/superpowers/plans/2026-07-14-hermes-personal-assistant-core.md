# Hermes Personal Assistant Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Evolve the current Telegram bot into a maintainable personal learning assistant whose knowledge, memory, and jobs use local SQLite while preserving working Telegram and ingestion behavior.

**Architecture:** Add a focused `hermes/` package and keep existing `core/` modules as temporary adapters. Cut over one state boundary at a time, beginning with analysis correctness and knowledge, then memory, jobs, Telegram routing, and backup. SQLite at `D:\HermesData\hermes.db` becomes the only transactional source of truth; Drive receives verified backups and exports.

**Tech Stack:** Python 3.12, standard-library `sqlite3`, SQLite FTS5/WAL, python-telegram-bot, requests, and `unittest` regression coverage.

**Implementation status (2026-07-15):** Complete and cut over on laptop 1. The implementation deliberately keeps `PersonalAssistant` as a context/routing helper instead of a larger orchestrator, returns strings through the compatibility LLM API while exposing typed capability/structured-output errors in `hermes.llm`, and exports full JSON rather than maintaining a second Markdown backup format.

## Global Constraints

- Preserve current Telegram command compatibility through hidden aliases.
- Never write transactional state to Google Drive JSON after cutover.
- Never create a lesson without source-bound evidence.
- Only approved lessons and approved memories may enter normal answer context.
- Do not implement video generation, vector search, multi-agent orchestration, or a plugin framework.
- Do not expose 9Router outside localhost/trusted private networking.
- Do not commit credentials or user data.

---

### Task 1: Stop false source-bound media analysis

**Files:**
- Modify: `tools/video_analyser.py`
- Modify: `core/job_watcher.py`
- Create: `tests/hermes/test_media_analysis_contract.py`

**Interfaces:**
- Produces: `MediaAnalysisUnavailable`, raised when no real model result exists.
- Consumes: existing `analyze_video(filepath, prompt_text=...)` call in `JobWorker`.

- [x] Write a test proving failed Gemini initialization raises instead of returning an offline prompt.
- [x] Run `.venv\Scripts\python.exe -m unittest tests.hermes.test_media_analysis_contract -v`; expect failure because the exception contract does not exist.
- [x] Add `MediaAnalysisUnavailable` and make normal `analyze_video` failures raise it. Keep `offline_only=True` available only for explicit non-learning inspection.
- [x] Update `JobWorker` to use transcript fallback or `needs_source`; never set high confidence after the exception.
- [x] Run the new test and `scripts/test_learning_fallback.py`; expect both to pass.

### Task 2: Add the SQLite foundation

**Files:**
- Create: `hermes/__init__.py`
- Create: `hermes/config.py`
- Create: `hermes/db.py`
- Create: `tests/hermes/test_database.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `Database(path=None)`, `Database.connect()`, `Database.transaction()`, and `Database.initialize()`.
- Database path: `HERMES_DB_PATH`, default `D:\HermesData\hermes.db` on Windows.

- [x] Write tests for schema creation, foreign keys, WAL mode, transaction rollback, and FTS5 availability.
- [x] Run the database tests; expect import failure for `hermes.db`.
- [x] Implement path resolution and schema migration version 1 for sources, artifacts, evidence, lessons, events, messages, memories, jobs, and FTS.
- [x] Run database tests; expect all to pass.

### Task 3: Implement SQLite knowledge and lifecycle migration

**Files:**
- Create: `hermes/knowledge.py`
- Create: `hermes/migration.py`
- Create: `scripts/migrate_knowledge_to_sqlite.py`
- Create: `tests/hermes/test_knowledge_repository.py`
- Create: `tests/hermes/test_knowledge_migration.py`
- Modify: `core/knowledge_store.py`
- Modify: `core/job_watcher.py`

**Interfaces:**
- Produces: `SQLiteKnowledgeStore` with compatibility methods `add_entry`, `get_entry`, `get_entry_detail`, `list_entries`, `get_approved_entries`, `get_approved_context`, `mark_approved`, `mark_rejected`, `mark_needs_reanalysis`, and `replace_pending_lesson`.
- Produces: `migrate_legacy_knowledge(source_root, database, dry_run=True) -> MigrationReport`.

- [x] Write repository tests for owner isolation, pending/approved/rejected transitions, event history, approved-only FTS retrieval, evidence, source dedupe, and approve-all-by-source.
- [x] Run repository tests; expect import failure.
- [x] Implement `SQLiteKnowledgeStore` with parameterized SQL and transactions.
- [x] Write migration tests using a legacy JSON fixture containing all three statuses and malformed optional details.
- [x] Run migration tests; expect failure until the importer exists.
- [x] Implement idempotent import preserving IDs, status, history, source metadata, detail content, and reanalysis flags.
- [x] Add backend selection to `core.knowledge_store.get_store()` using `HERMES_STORAGE_BACKEND=sqlite|json`.
- [x] Replace production `UnifiedKnowledgeStore()` instantiations in `core/job_watcher.py` with `get_store()`.
- [x] Run legacy knowledge tests and the new SQLite tests.

### Task 4: Add approved personal memory

**Files:**
- Create: `hermes/memory.py`
- Create: `tests/hermes/test_memory_repository.py`
- Modify: `core/conversation_memory.py`

**Interfaces:**
- Produces: `MemoryRepository.add_message`, `conversation_context`, `propose`, `approve`, `reject`, `deactivate`, and `approved_context`.
- `core.conversation_memory.get_memory()` remains compatible with `add`, `context`, and `clear`.

- [x] Write tests for bounded per-owner conversation context and pending memory exclusion.
- [x] Run tests; expect import failure.
- [x] Implement SQLite message retention and memory lifecycle events.
- [x] Adapt `core.conversation_memory` to select SQLite when configured while keeping the JSON implementation for migration tests.
- [x] Run new memory tests and `scripts/test_conversation_memory.py`.

### Task 5: Replace the duplicate job state machine

**Files:**
- Create: `hermes/jobs.py`
- Create: `tests/hermes/test_job_repository.py`
- Modify: `core/agent_jobs.py`
- Modify: `core/job_watcher.py`

**Interfaces:**
- Produces: `JobRepository.enqueue`, `claim_next`, `complete`, `fail`, `cancel`, `retry`, `recover_interrupted`, and `list_jobs`.
- Existing `AgentJobManager` public responses remain compatible with Telegram handlers.

- [x] Write tests for state transitions, owner isolation, atomic claim, restart recovery, bounded retry, and cooperative cancellation.
- [x] Run tests; expect import failure.
- [x] Implement the SQLite queue using `BEGIN IMMEDIATE` for atomic claims.
- [x] Make `AgentJobManager` use the SQLite repository when configured and stop creating the manifest queue mirror.
- [x] Make `JobWorker` claim SQLite jobs while preserving artifact output directories.
- [x] Run job tests and verify no new manifest task remains stuck in `running`.

### Task 6: Persist evidence-first learning results

**Files:**
- Create: `hermes/learning.py`
- Create: `tests/hermes/test_learning_service.py`
- Modify: `core/job_watcher.py`

**Interfaces:**
- Produces: `SourceBundle`, `EvidenceItem`, `LessonCandidate`, and `LearningResult` dataclasses.
- Produces: `LearningService.persist_result(result, owner_user_id, job_id)`.

- [x] Write tests for transcript evidence, image evidence, metadata-only summary, no-source behavior, atomic lessons, malformed structured output, and reanalysis.
- [x] Run tests; expect import failure.
- [x] Implement validation that requires evidence for every lesson and blocks metadata-only lessons.
- [x] Adapt `JobWorker` output to construct and persist `LearningResult` while retaining concise Telegram delivery artifacts.
- [x] Run learning recovery, TikTok resolver, transcript fallback, and new learning tests.

### Task 7: Introduce the assistant orchestrator and compact Telegram UX

**Files:**
- Create: `hermes/assistant.py`
- Create: `tests/hermes/test_personal_assistant.py`
- Modify: `telegram_bot.py`
- Modify: `scripts/test_telegram_learning_delivery.py`

**Interfaces:**
- Produces: `PersonalAssistant.build_context(owner_user_id, chat_id, user_text) -> AssistantContext`.
- Public commands: `/learn`, `/knowledge`, `/jobs`, `/remember`, `/settings`, `/help`.

- [x] Write routing tests for natural learning, knowledge-first answers, live-search labeling, memory proposals, and command aliases.
- [x] Run tests; expect failure because the orchestrator does not exist.
- [x] Implement deterministic routing and context assembly from approved knowledge, approved memory, and bounded messages.
- [x] Route normal Telegram chat through `HermesAssistant` and keep old commands registered as aliases.
- [x] Add per-lesson approval and approve-all-by-source actions with slash-command fallback.
- [x] Run Telegram authorization, HTML rendering, learning delivery, repository search, and assistant tests.

### Task 8: Strengthen the LLM gateway boundary

**Files:**
- Modify: `core/llm_gateway.py`
- Create: `hermes/llm.py`
- Create: `tests/hermes/test_llm_gateway.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `HermesLLMGateway.complete()`, `structured()`, `CapabilityMismatchError`, and `StructuredOutputError`.
- The compatibility gateway logs requested task/model, actual model, duration, retries, and sanitized failures.

- [x] Write tests for task aliases, capability rejection, timeout, sanitized errors, structured result metadata, and disabled legacy fallback.
- [x] Run tests; expect failure for the new result contract.
- [x] Implement the typed wrapper around the existing 9Router client.
- [x] Default legacy provider fallback to disabled and retain explicit opt-in compatibility.
- [x] Run gateway tests and a health check against local 9Router when available.

### Task 9: Backup, export, restore, and retention

**Files:**
- Create: `hermes/backup.py`
- Create: `scripts/hermes_backup.py`
- Create: `tests/hermes/test_backup.py`
- Create: `docs/runbooks/hermes-sqlite-backup-restore.md`

**Interfaces:**
- Produces: `SQLiteBackupManager.create_backup`, `verify`, `export_json`, `restore`, and bounded backup/job retention.

- [x] Write tests proving a live WAL database is backed up consistently and a corrupt backup is rejected.
- [x] Run tests; expect import failure.
- [x] Implement SQLite backup API usage, integrity checks, full JSON export, guarded restore, and configurable retention.
- [x] Document laptop 1 active and laptop 2 passive restore procedure.
- [x] Run backup tests and a temporary-directory restore smoke test.

### Task 10: Migration cutover and final verification

**Files:**
- Modify: `.env.example`
- Create: `docs/runbooks/hermes-sqlite-cutover.md`

**Interfaces:**
- Consumes all repositories and migration commands from earlier tasks.
- Produces a verified local `D:\HermesData\hermes.db` and a rollback snapshot.

- [x] Stop bot and worker processes before cutover.
- [x] Back up legacy knowledge and run migration in dry-run mode.
- [x] Compare total/status/source counts and report malformed/orphan records.
- [x] Run the real idempotent migration and `PRAGMA integrity_check`.
- [x] Set `HERMES_STORAGE_BACKEND=sqlite` and `HERMES_DB_PATH=D:\HermesData\hermes.db` locally without committing secrets.
- [x] Run the complete standalone test suite plus new `unittest` modules.
- [x] Start Telegram and worker, submit a text learning smoke job, approve one lesson, retrieve it, and verify restart persistence.
- [x] Create and verify the first Google Drive backup/export.
