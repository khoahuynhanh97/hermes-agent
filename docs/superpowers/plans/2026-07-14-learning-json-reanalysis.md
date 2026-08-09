# Learning JSON Reanalysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show `/re_analysis <id>` only for pending lessons whose knowledge JSON failed twice, and re-run analysis into the same entry.

**Architecture:** Keep media ingestion and normal pending lessons unchanged. Persist a small `needs_reanalysis` flag and recovery metadata on malformed-JSON placeholders, expose one owner-authorized Telegram command, and let the existing worker update the targeted pending entry after a successful manual rerun.

**Tech Stack:** Python, python-telegram-bot, local JSON knowledge store, existing `AgentJobManager` and `JobWorker`.

## Global Constraints

- Do not show `/re_analysis` for valid pending lessons or `needs_source` download failures.
- Do not invent a summary when structured extraction fails.
- Reanalysis must keep the same knowledge ID and remain pending for approval.
- One command creates one job; no automatic retry loop.
- Preserve the current Google Drive knowledge root and Telegram authorization rules.

---

### Task 1: Persist JSON-Reanalysis State

**Files:**
- Modify: `core/knowledge_store.py`
- Modify: `scripts/test_learning_recovery.py`

**Interfaces:**
- Produces: `UnifiedKnowledgeStore.get_entry_detail(identifier: str) -> dict`
- Produces: `UnifiedKnowledgeStore.mark_needs_reanalysis(identifier: str, error: str, detail_updates: dict | None = None) -> dict | None`
- Produces: `UnifiedKnowledgeStore.replace_pending_lesson(identifier: str, lesson: dict, detail_data: dict) -> dict | None`

- [ ] **Step 1: Write failing store tests**

Add checks that a pending entry can be marked with top-level `needs_reanalysis`, that the detail file records `validation_error` and `reanalysis_count`, and that replacing the lesson keeps its ID while clearing the flag.

```python
entry = store.add_entry(title="Malformed JSON", source_url="https://example/video")
marked = store.mark_needs_reanalysis(entry["id"], "invalid JSON", {"original_job_id": "job_1"})
assert marked["needs_reanalysis"] is True
assert store.get_entry_detail(entry["id"])["reanalysis_count"] == 0

updated = store.replace_pending_lesson(
    entry["id"],
    {"title": "Recovered lesson", "category": "Technology", "key_lessons": ["Validated"]},
    {"summary": "Recovered from source analysis."},
)
assert updated["id"] == entry["id"]
assert updated["needs_reanalysis"] is False
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv\Scripts\python.exe scripts\test_learning_recovery.py`

Expected: FAIL because the three store methods do not exist.

- [ ] **Step 3: Implement atomic entry/detail updates**

Reload the index before mutation, reject non-pending entries in `replace_pending_lesson`, preserve ownership/source/history fields, write the detail JSON, then atomically save the index.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv\Scripts\python.exe scripts\test_learning_recovery.py`

Expected: `learning recovery checks: PASS`.

### Task 2: Create a Placeholder Only After Two JSON Failures

**Files:**
- Modify: `core/job_watcher.py`
- Modify: `scripts/test_learning_recovery.py`

**Interfaces:**
- Consumes: `mark_needs_reanalysis(...)` from Task 1.
- Produces: a pending knowledge entry with `needs_reanalysis: true` and `__KNOWLEDGE_ENTRY__:<id>` only when source-bound analysis is recoverable and both JSON calls fail.

- [ ] **Step 1: Write a failing worker regression test**

Patch both structured model calls to return malformed text, execute a knowledge job with source-bound analysis, and assert:

```python
assert entry["status"] == "pending"
assert entry["needs_reanalysis"] is True
assert f"__KNOWLEDGE_ENTRY__:{entry['id']}" in files_created
assert "__KNOWLEDGE_RECOVERY__" not in "\n".join(files_created)
```

Also test that `metadata_only` and `needs_source` paths create no reanalysis placeholder.

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv\Scripts\python.exe scripts\test_learning_recovery.py`

Expected: FAIL because the current worker emits a job recovery marker without a knowledge entry.

- [ ] **Step 3: Implement the bounded failure branch**

Use the existing raw analysis, source URL, owner, job output directory, and validation error to create/update a pending placeholder. Store `original_job_id`, `analysis_source`, `confidence`, `raw_analysis`, and `reanalysis_count: 0`. Return the normal knowledge-entry marker so Telegram reports one pending lesson.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv\Scripts\python.exe scripts\test_learning_recovery.py`

Expected: PASS with no placeholder for low-confidence source failures.

### Task 3: Add Telegram Listing and `/re_analysis`

**Files:**
- Modify: `telegram_bot.py`
- Modify: `scripts/test_telegram_learning_delivery.py`

**Interfaces:**
- Consumes: `needs_reanalysis` from the index and detail/source metadata from Task 1.
- Produces: `re_analysis_command(update, context)`.
- Extends: `build_video_job(..., bypass_dedup: bool = False, reanalysis_target_id: str = "")`.

- [ ] **Step 1: Write failing formatter and command tests**

Verify the HTML formatter adds the command only to a flagged entry:

```python
assert "<code>/re_analysis kb_bad</code>" in malformed_listing
assert "/re_analysis" not in valid_listing
```

Verify unauthorized users are rejected, valid lessons are rejected, and a valid command creates exactly one job with `reanalysis_target_id` while bypassing source deduplication.

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv\Scripts\python.exe scripts\test_telegram_learning_delivery.py`

Expected: FAIL because the formatter action and command do not exist.

- [ ] **Step 3: Implement the Telegram command**

Load the flagged pending entry and detail, enforce ownership, then call `build_video_job` with the stored source, `bypass_dedup=True`, and the target ID. Persist the target ID in both inbox job JSON and project `job.json`. Register only `CommandHandler("re_analysis", re_analysis_command)`.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv\Scripts\python.exe scripts\test_telegram_learning_delivery.py`

Expected: `telegram learning delivery checks: PASS`.

### Task 4: Update the Same Entry From the Reanalysis Job

**Files:**
- Modify: `core/job_watcher.py`
- Modify: `scripts/test_learning_recovery.py`

**Interfaces:**
- Consumes: job field `reanalysis_target_id` and `replace_pending_lesson(...)`.
- Produces: same-ID success update or same-ID failure accounting.

- [ ] **Step 1: Write failing success/failure tests**

For a validated result, assert the target ID is unchanged, the title/summary are replaced, `needs_reanalysis` is false, and status stays pending. For another JSON failure, assert `reanalysis_count` increments and the flag remains true.

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv\Scripts\python.exe scripts\test_learning_recovery.py`

Expected: FAIL because the worker currently uses URL deduplication rather than an explicit target update.

- [ ] **Step 3: Route success and failure through the target entry**

If `reanalysis_target_id` is present, call `replace_pending_lesson` after validation. If both JSON attempts fail, call `mark_needs_reanalysis` with an incremented counter and latest error. Never append a second entry.

- [ ] **Step 4: Run focused and regression verification**

Run:

```powershell
.venv\Scripts\python.exe scripts\test_learning_recovery.py
.venv\Scripts\python.exe scripts\test_telegram_learning_delivery.py
.venv\Scripts\python.exe scripts\test_learning_fallback.py
.venv\Scripts\python.exe scripts\test_tiktok_media_resolver.py
.venv\Scripts\python.exe -m compileall -q telegram_bot.py core\job_watcher.py core\knowledge_store.py
```

Expected: all scripts print `PASS`; compileall exits zero.

### Task 5: Runtime Check

**Files:**
- No source changes expected.

**Interfaces:**
- Verifies bot and worker use the updated files.

- [ ] Stop the existing Telegram bot and job worker processes.
- [ ] Start both from `.venv` with dedicated log files.
- [ ] Confirm Telegram logs contain `Application started` and worker logs contain the inbox-listening message.
- [ ] Run `/knowledge pending` and confirm only malformed-JSON placeholders show `/re_analysis <id>`.
