# Hermes Foundation and Data Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the active Hermes runtime, consolidate knowledge lifecycle transitions, safely audit and repair deterministic SQLite defects, and complete a verified maintenance run.

**Architecture:** A deep `KnowledgeLifecycle` module becomes the production seam for lesson transitions. `DataHealth` produces and applies deterministic repair plans, while `MaintenanceRunner` orchestrates process control, verified backup, repair, post-checks, restart, and redacted reporting without owning lifecycle rules.

**Tech Stack:** Python 3.11+, SQLite/FTS5, `unittest`, python-telegram-bot, PowerShell process control, existing Hermes adapters and scripts.

## Global Constraints

- SQLite is the only authoritative knowledge store; never reconcile legacy JSON back into SQLite.
- Do not delete lessons, sources, evidence, events, or backups.
- Do not call an LLM or external provider during data repair.
- Defective lessons are rejected and retained with lifecycle history.
- Create and verify a complete backup before touching live data.
- Stop the Telegram bot and worker for the live maintenance transaction.
- A failed post-check leaves runtime stopped and reports `manual_intervention_required`.
- Reports must omit lesson content, evidence excerpts, private URLs, Telegram IDs, credentials, cookies, tokens, and environment values.
- Preserve unrelated worktree changes and stage only files owned by each task.

---

### Task 1: Restore the Existing Runtime Contract

**Files:**
- Create: `hermes/migration/legacy_knowledge.py`
- Modify: `hermes/migration/__init__.py`
- Modify: `telegram_bot.py`
- Modify: `tests/hermes/test_telegram_text_learning.py`
- Modify: `tests/hermes/test_telegram_memory.py`
- Modify: `tests/hermes/test_url_ingestion.py`
- Test: `tests/hermes/test_knowledge_migration.py`

**Interfaces:**
- Consumes: existing `MemoryRepository`, `extract_memory_request()`, `extract_learning_request()`, `inspect_url()`, and `SQLiteKnowledgeStore.approve_source()`.
- Produces: `save_text_learning_source(text, owner_user_id)`, Telegram memory/settings/source-approval/reanalysis handlers, and importable `migrate_legacy_knowledge`.

- [ ] **Step 1: Make migration imports target the package**

Move the existing implementation from `hermes/migration.py` into
`hermes/migration/legacy_knowledge.py` and export the public names:

```python
# hermes/migration/__init__.py
from .legacy_knowledge import MigrationReport, migrate_legacy_knowledge

__all__ = ["MigrationReport", "migrate_legacy_knowledge"]
```

- [ ] **Step 2: Run the migration test**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.hermes.test_knowledge_migration -v
```

Expected: one test passes; no import error.

- [ ] **Step 3: Add failing Telegram routing and persistence tests**

Keep the existing assertions and add registration checks:

```python
def test_primary_commands_are_registered(self):
    source = Path("telegram_bot.py").read_text(encoding="utf-8")
    for command in (
        "remember", "approve_memory", "reject_memory",
        "approve_source", "re_analysis", "settings",
    ):
        self.assertIn(f'CommandHandler("{command}"', source)
```

The natural learning and natural memory tests must patch the LLM with an
exception and prove no LLM call occurs.

- [ ] **Step 4: Run the Telegram and URL tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.test_telegram_text_learning `
  tests.hermes.test_telegram_memory `
  tests.hermes.test_url_ingestion -v
```

Expected: failures identify the missing functions/handlers and website branch.

- [ ] **Step 5: Implement local text persistence and early intent routing**

Add:

```python
def save_text_learning_source(text: str, owner_user_id: str | int) -> tuple[Path, dict]:
    payload = (text or "").strip()
    if not payload:
        raise ValueError("Learning text cannot be empty")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    root = Path(os.environ.get("HERMES_DATA_DIR", config.HERMES_DATA_DIR)).resolve()
    target_dir = root / "learning_sources" / str(owner_user_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"text-{digest[:16]}.txt"
    temporary = target.with_suffix(".txt.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(target)
    return target, {"sha256": digest, "bytes": len(payload.encode("utf-8"))}
```

At the beginning of `default_chat_handler`, before generic route/LLM handling:

```python
memory_text = extract_memory_request(user_text)
if memory_text:
    await propose_memory(update, memory_text)
    return

learning_text = extract_learning_request(user_text)
if learning_text:
    await create_video_job_command(
        update, context, mode=MODE_LEARN_KNOWLEDGE,
        explicit_source_text=learning_text,
    )
    return
```

Extend the handler with an explicit parameter and select the persisted file as
the job source:

```python
async def create_video_job_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str,
    *,
    explicit_source_text: str = "",
):
    if explicit_source_text:
        owner_id = update.effective_user.id
        source_path, source_meta = save_text_learning_source(
            explicit_source_text, owner_id
        )
        return await enqueue_learning_job(
            update,
            mode=mode,
            source_value=str(source_path),
            source_kind="text",
            source_metadata=source_meta,
        )
    # Existing URL/attachment selection continues through enqueue_learning_job.
```

Extract the existing final job creation/reply block into
`enqueue_learning_job(update, *, mode, source_value, source_kind,
source_metadata=None)` so URL, attachment, and plain-text inputs share one
enqueue path.

- [ ] **Step 6: Implement the website ingestion branch**

Before calling `fetch_transcript()` in `build_video_job`:

```python
if source_kind == "website_url":
    inspected = inspect_url(source_value)
    job["source"].update(
        transcript=inspected["text"],
        transcript_method="website_text",
        metadata={
            "title": inspected["title"],
            "description": inspected["description"],
            "content_type": inspected["content_type"],
            "bytes_read": inspected["bytes_read"],
        },
        fetch_status="success",
        fetch_confidence="medium",
    )
    manager._write_json(Path(job["paths"]["job_file"]), job)
    manager._write_json(Path(job["target"]["output_dir"]) / "job.json", job)
    return job
```

- [ ] **Step 7: Restore explicit memory, source approval, reanalysis, and settings handlers**

Use `MemoryRepository` for proposal/decision operations. `settings_command`
reports only storage backend name, database filename, 9Router health, and model
aliases; it never prints environment values.

`approve_source_command` resolves a lesson owned by the caller and passes its
`source_id` to the lifecycle module introduced in Task 2. Until Task 2 lands,
the test may use the existing `store.approve_source`.

`re_analysis_command` validates owner and pending/`needs_reanalysis`, then
creates a job with `reanalysis_target_id`.

Register all six commands in `main()`.

- [ ] **Step 8: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.test_knowledge_migration `
  tests.hermes.test_telegram_text_learning `
  tests.hermes.test_telegram_memory `
  tests.hermes.test_url_ingestion -v
```

Expected: all tests pass without network calls or timeouts.

- [ ] **Step 9: Commit**

```powershell
git add hermes/migration/__init__.py hermes/migration/legacy_knowledge.py `
  telegram_bot.py tests/hermes/test_telegram_text_learning.py `
  tests/hermes/test_telegram_memory.py tests/hermes/test_url_ingestion.py
git commit -m "fix: restore Hermes runtime contracts"
```

---

### Task 2: Introduce the KnowledgeLifecycle Seam

**Files:**
- Create: `hermes/application/knowledge_lifecycle.py`
- Modify: `hermes/knowledge.py`
- Modify: `core/knowledge_store.py`
- Create: `tests/hermes/application/test_knowledge_lifecycle.py`
- Modify: `tests/hermes/test_knowledge_repository.py`

**Interfaces:**
- Consumes: `SQLiteKnowledgeStore.get_entry()`, lifecycle events, and FTS sync.
- Produces: `LifecycleActor`, `LifecycleCommand`, `LifecycleResult`, and `KnowledgeLifecycle`.

- [ ] **Step 1: Write failing lifecycle tests**

Cover owner isolation, system actor permission, forbidden approval,
idempotency, event count, FTS inclusion/removal, batch atomicity, and
`force=True` compatibility:

```python
actor = LifecycleActor.owner("42")
result = lifecycle.approve(entry["id"], actor, mode="test")
self.assertTrue(result.ok)
self.assertTrue(result.changed)
self.assertEqual(result.lesson["status"], "approved")

again = lifecycle.approve(entry["id"], actor, mode="test")
self.assertTrue(again.ok)
self.assertFalse(again.changed)
```

- [ ] **Step 2: Run the tests to verify failure**

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.application.test_knowledge_lifecycle -v
```

Expected: import failure for the new lifecycle module.

- [ ] **Step 3: Define lifecycle types and interface**

```python
@dataclass(frozen=True)
class LifecycleActor:
    actor_id: str
    role: Literal["owner", "system"] = "owner"

    @classmethod
    def owner(cls, actor_id: str | int) -> "LifecycleActor":
        return cls(str(actor_id), "owner")

    @classmethod
    def system(cls, name: str) -> "LifecycleActor":
        return cls(name, "system")


@dataclass(frozen=True)
class LifecycleCommand:
    action: Literal["approve", "reject", "request_reanalysis"]
    lesson_id: str
    actor: LifecycleActor
    mode: str = ""
    reason: str = ""
    expected_status: str | None = None
    force: bool = False


@dataclass(frozen=True)
class LifecycleResult:
    ok: bool
    code: str
    changed: bool
    lesson: dict | None = None
```

`KnowledgeLifecycle.apply(commands)` returns one result per command and executes
the complete batch atomically.

- [ ] **Step 4: Add one transactional SQLite implementation**

Add `SQLiteKnowledgeStore.apply_lifecycle_commands(commands)` and implement all
owner checks, state checks, event writes, timestamps, and FTS updates inside
one `transaction(immediate=True)`.

Compatibility methods `mark_approved`, `mark_rejected`, and `approve_source`
must build lifecycle commands and call the same internal implementation.
`mark_approved` accepts `force: bool = False` on both JSON and SQLite backends.

- [ ] **Step 5: Run lifecycle and repository tests**

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.application.test_knowledge_lifecycle `
  tests.hermes.test_knowledge_repository -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add hermes/application/knowledge_lifecycle.py hermes/knowledge.py `
  core/knowledge_store.py tests/hermes/application/test_knowledge_lifecycle.py `
  tests/hermes/test_knowledge_repository.py
git commit -m "feat: centralize knowledge lifecycle transitions"
```

---

### Task 3: Wire Every Production Lifecycle Caller

**Files:**
- Modify: `telegram_bot.py`
- Modify: `core/learning_review.py`
- Create: `tests/hermes/test_knowledge_lifecycle_wiring.py`
- Modify: `tests/hermes/test_telegram_memory.py`

**Interfaces:**
- Consumes: `KnowledgeLifecycle` and `LifecycleActor` from Task 2.
- Produces: Telegram command/callback/bulk/source and GUI review paths that all cross the lifecycle seam.

- [ ] **Step 1: Write failing wiring tests**

Patch `KnowledgeLifecycle` and assert command, callback, bulk, source approval,
force approval, and `LearningReviewStore` invoke it. Also scan production files
to reject new direct calls to `mark_approved` and `mark_rejected`.

- [ ] **Step 2: Run wiring tests to verify failure**

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.test_knowledge_lifecycle_wiring -v
```

Expected: direct-store call assertions fail.

- [ ] **Step 3: Replace direct transitions**

Instantiate `KnowledgeLifecycle(get_store())` once per handler operation.
Translate lifecycle result codes into existing Telegram messages. Keep owner
checks in the lifecycle module; handlers only validate command shape.

For GUI review, use `LifecycleActor.system("gui-review")` and preserve the
proposal-file move only after lifecycle success.

- [ ] **Step 4: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.test_knowledge_lifecycle_wiring `
  tests.hermes.test_telegram_memory `
  tests.hermes.test_knowledge_repository -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add telegram_bot.py core/learning_review.py `
  tests/hermes/test_knowledge_lifecycle_wiring.py `
  tests/hermes/test_telegram_memory.py
git commit -m "refactor: route production knowledge decisions through lifecycle"
```

---

### Task 4: Build DataHealth Audit and Safe Repair

**Files:**
- Create: `hermes/data_health.py`
- Create: `tests/hermes/test_data_health.py`

**Interfaces:**
- Consumes: `Database`, `KnowledgeLifecycle.apply()`, and SQLite lifecycle/FTS schema.
- Produces: `Finding`, `RepairAction`, `AuditReport`, `RepairPlan`, `RepairReport`, and `DataHealth`.

- [ ] **Step 1: Write failing audit tests**

Use temporary databases to assert detection of FTS drift, missing approval
timestamps, deterministic defects, evidence gaps, and legacy drift. Hash the
database before/after `audit()` to prove it performs no writes.

- [ ] **Step 2: Run tests to verify failure**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.hermes.test_data_health -v
```

Expected: import failure for `hermes.data_health`.

- [ ] **Step 3: Define reports and deterministic action IDs**

```python
@dataclass(frozen=True)
class Finding:
    code: str
    severity: Literal["info", "warning", "error"]
    subject_type: str
    subject_id_hash: str
    repair_class: Literal["safe", "review", "forbidden"]
    metadata: dict[str, int | str | bool]


@dataclass(frozen=True)
class RepairAction:
    action_id: str
    kind: Literal["rebuild_fts", "set_approved_at", "reject_lesson"]
    subject_id: str
    expected: dict[str, int | str | bool]
```

Reports expose aggregate counts and hashed IDs, not lesson content or URLs.

- [ ] **Step 4: Implement read-only audit**

Audit:

- `integrity_check` and `foreign_key_check`.
- FTS missing/extra/orphan/mismatched rows.
- Approved lessons missing `approved_at`.
- Lessons matching the three approved deterministic defect rules.
- Approved lessons without evidence as review-only.
- Schema version and aggregate lifecycle counts.

- [ ] **Step 5: Implement atomic repair**

`repair(plan)` opens one immediate transaction, rechecks every precondition,
updates unambiguous timestamps, applies lifecycle rejection commands through
the shared SQLite transition implementation, rebuilds FTS, and rolls back the
whole repair on any exception.

- [ ] **Step 6: Add rollback and idempotency tests**

Inject a failure after one action and assert no row/event/FTS change remains.
Run the same successful plan twice and assert the second run reports zero
changes.

- [ ] **Step 7: Run tests**

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.test_data_health `
  tests.hermes.application.test_knowledge_lifecycle `
  tests.hermes.test_knowledge_repository -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```powershell
git add hermes/data_health.py tests/hermes/test_data_health.py
git commit -m "feat: audit and repair deterministic knowledge defects"
```

---

### Task 5: Strengthen Backup Verification

**Files:**
- Modify: `hermes/backup.py`
- Modify: `scripts/hermes_backup.py`
- Modify: `tests/hermes/test_backup.py`

**Interfaces:**
- Consumes: `Database` and existing SQLite backup interface.
- Produces: `BackupVerification` data containing integrity, FK, schema, required tables, and aggregate counts.

- [ ] **Step 1: Write failing verification tests**

Test valid backup counts, missing table, FK violation, corrupt file, read-only
reopen, and no pruning before the new backup verifies.

- [ ] **Step 2: Run tests to verify failure**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.hermes.test_backup -v
```

Expected: new verification assertions fail.

- [ ] **Step 3: Implement complete verification**

Return:

```python
{
    "ok": bool,
    "path": str,
    "integrity": "ok",
    "foreign_key_violations": int,
    "schema_version": int,
    "required_tables_missing": list[str],
    "counts": {"lessons": int, "sources": int, "lesson_events": int},
    "detail": str,
}
```

Use `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, `PRAGMA user_version`,
required table lookup, aggregate counts, and immutable read-only reopen.

- [ ] **Step 4: Run tests**

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.test_backup tests.hermes.test_database -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add hermes/backup.py scripts/hermes_backup.py tests/hermes/test_backup.py
git commit -m "feat: verify complete Hermes backups"
```

---

### Task 6: Implement MaintenanceRunner and Redacted Reports

**Files:**
- Create: `hermes/maintenance.py`
- Create: `tests/hermes/test_maintenance.py`

**Interfaces:**
- Consumes: `SQLiteBackupManager`, `DataHealth`, `ProcessController`, and a report directory.
- Produces: `MaintenanceRunner.run() -> MaintenanceResult`.

- [ ] **Step 1: Write failing orchestration tests**

Use fake process, backup, and data-health adapters. Cover success, ambiguous
process state, shutdown timeout, backup failure, repair failure, post-check
failure, partial restart failure, resumability, and report redaction.

- [ ] **Step 2: Run tests to verify failure**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.hermes.test_maintenance -v
```

Expected: import failure for `hermes.maintenance`.

- [ ] **Step 3: Define process and result interfaces**

```python
class ProcessController(Protocol):
    def discover(self) -> RuntimeState: ...
    def stop(self, state: RuntimeState, timeout_seconds: int) -> None: ...
    def start(self, state: RuntimeState) -> RuntimeState: ...
    def verify(self, state: RuntimeState) -> dict[str, bool]: ...


@dataclass(frozen=True)
class MaintenanceResult:
    run_id: str
    status: Literal["completed", "failed", "manual_intervention_required"]
    backup_path: str
    report_json: str
    report_markdown: str
```

- [ ] **Step 4: Implement the state machine**

Persist each completed stage in a redacted run-state JSON file. Restart only
after backup verification, repair, and post-audit invariants pass. If only one
process restarts, stop it and return failure.

- [ ] **Step 5: Implement report allowlisting**

Serialize only run metadata, aggregate counts, hashed finding/action IDs,
verification booleans, and process outcomes. Add a recursive redaction test
that rejects keys containing `content`, `excerpt`, `url`, `token`, `cookie`,
`credential`, `telegram`, or `environment`.

- [ ] **Step 6: Run tests**

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.test_maintenance tests.hermes.test_data_health `
  tests.hermes.test_backup -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add hermes/maintenance.py tests/hermes/test_maintenance.py
git commit -m "feat: orchestrate safe Hermes maintenance"
```

---

### Task 7: Add Windows Runtime Control and Maintenance CLI

**Files:**
- Create: `hermes/adapters/local/windows_runtime_processes.py`
- Create: `scripts/hermes_maintenance.py`
- Create: `tests/hermes/test_windows_runtime_processes.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `ProcessController` from Task 6 and existing Python entrypoints.
- Produces: `WindowsHermesProcessController` and `scripts/hermes_maintenance.py run|audit`.

- [ ] **Step 1: Write failing adapter and CLI tests**

Patch PowerShell invocation and assert exact matching of:

- `telegram_bot.py`
- `scripts/run_job_worker.py`

Reject zero, duplicate, or unexpected matching processes. Assert restart uses
the repository `.venv` Python and hidden windows with existing runtime logs.

- [ ] **Step 2: Run tests to verify failure**

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.test_windows_runtime_processes -v
```

Expected: import failure for the adapter.

- [ ] **Step 3: Implement the Windows adapter**

Use PowerShell/CIM read-only discovery, `Stop-Process` for resolved PIDs, and
`Start-Process -WindowStyle Hidden` with explicit executable, argument,
working-directory, stdout, and stderr paths. Never build a command from
database content or user input.

- [ ] **Step 4: Implement CLI safety gates**

Commands:

```powershell
.\.venv\Scripts\python.exe scripts\hermes_maintenance.py audit
.\.venv\Scripts\python.exe scripts\hermes_maintenance.py run --confirm-live
```

`run` refuses without `--confirm-live`, refuses a non-SQLite backend, prints
only report paths/status, and exits nonzero for failed or manual-intervention
states.

- [ ] **Step 5: Run tests**

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.hermes.test_windows_runtime_processes `
  tests.hermes.test_maintenance -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add hermes/adapters/local/windows_runtime_processes.py `
  scripts/hermes_maintenance.py tests/hermes/test_windows_runtime_processes.py `
  .env.example
git commit -m "feat: add Windows Hermes maintenance command"
```

---

### Task 8: Full Verification, Runbook, and Live Maintenance

**Files:**
- Create: `docs/runbooks/hermes-foundation-maintenance.md`
- Modify: `docs/status/hermes-current-feature-report.md`
- Test: `tests/hermes/`

**Interfaces:**
- Consumes: all prior task interfaces and the live SQLite/runtime configuration.
- Produces: verified tests, a recovery runbook, a current backup, repaired live data, and redacted reports.

- [ ] **Step 1: Run all Hermes unit tests with a bounded timeout**

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests\hermes -v
```

Expected: all discovered tests pass and finish within 120 seconds.

- [ ] **Step 2: Run broader repository checks**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q hermes core tools telegram_bot.py scripts tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Expected: all commands exit 0. Pre-existing unrelated failures must be
diagnosed and fixed only when they block the approved runtime path.

- [ ] **Step 3: Write the operator runbook**

Document exact audit, live run, report inspection, process verification, backup
verification, and manual restore commands. State clearly that automatic
restore is never performed.

- [ ] **Step 4: Run read-only live audit**

```powershell
.\.venv\Scripts\python.exe scripts\hermes_maintenance.py audit
```

Expected: report shows current counts and only classified findings; no database
mtime/content change attributable to audit.

- [ ] **Step 5: Run live maintenance**

```powershell
.\.venv\Scripts\python.exe scripts\hermes_maintenance.py run --confirm-live
```

Expected: verified backup, deterministic repair, clean post-audit, bot and
worker restarted, status `completed`.

- [ ] **Step 6: Verify live outcomes**

Read-only checks must confirm:

- Latest backup lesson count equals the pre-repair live count.
- Defective lessons are retained and rejected.
- FTS row count equals approved lesson count with no mismatch.
- `integrity_check=ok` and zero FK violations.
- Exactly one bot and one worker process are healthy.
- Reports contain no forbidden keys or sensitive values.

- [ ] **Step 7: Update status documentation**

Record the actual test count, backup path/date, before/after aggregate counts,
maintenance status, and remaining review-only findings. Do not include lesson
content, URLs, user IDs, or secrets.

- [ ] **Step 8: Commit**

```powershell
git add docs/runbooks/hermes-foundation-maintenance.md `
  docs/status/hermes-current-feature-report.md
git commit -m "docs: record Hermes foundation maintenance"
```
