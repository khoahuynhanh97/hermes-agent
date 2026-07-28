# Hermes Foundation and Data Reliability Design

**Date:** 2026-07-29

**Status:** Approved in conversation; awaiting review of the written spec

## 1. Purpose

This design defines the first stabilization phase for Hermes Agent. The phase
protects the live SQLite knowledge base, consolidates lesson lifecycle changes
behind one production interface, audits and repairs deterministic data defects,
and restores the Telegram bot and worker after a short maintenance window.

This phase deliberately does not implement semantic vector search, Obsidian
auto-sync, automatic correction mining, or a redesigned media acquisition
pipeline. Those features depend on the lifecycle and operational guarantees
established here.

## 2. Current State

The production runtime starts `telegram_bot.py` and
`scripts/run_job_worker.py`. Newer modules under `apps/telegram/` and
`hermes/application/` are not yet the production path.

The live SQLite database is the authoritative store. At the time of design it
contains:

- 112 lessons: 99 approved and 13 pending.
- 99 FTS rows, matching the approved lesson count.
- Three pending lessons marked `needs_reanalysis`.
- Two pending lessons titled `Không xác định`.
- Three approved lessons in category `error`.
- Seventeen approved lessons without evidence.
- Four approved lessons without `approved_at`.

The newest local backup contains only 17 lessons. The working tree also
contains many unrelated modified and untracked paths, so implementation must
stage and commit only files owned by this phase.

## 3. Decisions

### 3.1 Implementation approach

Use a lifecycle-first approach. Do not patch each Telegram handler, callback,
GUI path, and repair script independently.

### 3.2 Maintenance policy

- Hermes may stop the Telegram bot and worker for a 5-10 minute maintenance
  window.
- The maintenance runner automatically applies deterministic safe repairs after
  a verified backup succeeds.
- Defective lessons are rejected and retained for audit; they are never deleted.
- SQLite is authoritative. Legacy JSON is not reconciled back into SQLite.

### 3.3 Content policy

This phase does not call an LLM and does not synthesize lesson content,
evidence, provenance, or events. Re-analysis requiring source interpretation is
deferred.

## 4. Architecture

### 4.1 KnowledgeLifecycle

Create a deep `KnowledgeLifecycle` module as the only supported production
interface for lesson state transitions:

```python
approve(lesson_id, actor, mode) -> LifecycleResult
reject(lesson_id, actor, reason) -> LifecycleResult
request_reanalysis(lesson_id, actor) -> LifecycleResult
replace_reanalyzed(lesson_id, proposal, actor) -> LifecycleResult
```

The implementation owns:

- Owner authorization.
- Allowed state transitions.
- `needs_reanalysis` enforcement.
- Duplicate approval policy.
- Event creation and idempotency.
- FTS synchronization.
- Transaction boundaries.

Telegram commands, callback handlers, GUI review actions, and maintenance
repairs must cross this seam. Existing SQLite repository operations remain
internal implementation details where possible.

### 4.2 DataHealth

Create a `DataHealth` module with two operations:

```python
audit() -> AuditReport
repair(plan: RepairPlan) -> RepairReport
```

`audit()` is read-only and returns structured findings. `repair()` accepts a
plan derived from a prior audit and applies only actions classified as safe.
Every action has a stable identifier, preconditions, before/after metadata, and
an outcome.

### 4.3 MaintenanceRunner

Create a `MaintenanceRunner` that coordinates process control, backup,
verification, audit, repair, post-checks, restart, and reporting.

It does not contain lifecycle or data-quality rules. It orchestrates the
`KnowledgeLifecycle`, `DataHealth`, backup adapter, process adapter, and report
writer through their interfaces.

## 5. Maintenance Flow

The runner performs these steps in order:

1. Discover the expected Telegram bot and worker processes and reject ambiguous
   process state.
2. Record enough process configuration to restart the same entrypoints.
3. Stop both processes gracefully and wait until SQLite has no active writer.
4. Create a timestamped SQLite backup using the SQLite backup interface.
5. Verify the backup with `integrity_check`, foreign-key checks, schema checks,
   required table checks, row-count capture, and a read-only reopen.
6. Audit the live database and persist the pre-repair report.
7. Build a repair plan and execute only safe actions.
8. Audit the live database again and compare required invariants and counts.
9. Restart the bot and worker only when all required post-checks pass.
10. Verify process health and inspect bounded startup-log output for fatal
    errors.
11. Write redacted JSON and Markdown reports.

The runner is resumable. Re-running it after a completed repair must produce no
additional lifecycle events or data mutations.

## 6. Repair Classification

### 6.1 Safe automatic repairs

- Rebuild FTS from approved lessons.
- Remove missing, extra, or orphaned FTS rows through a complete rebuild.
- Populate a missing `approved_at` only when exactly one approved lifecycle
  event provides an unambiguous timestamp.
- Reject lessons matching deterministic defect rules approved for this phase:
  `needs_reanalysis = 1`, exact normalized title `Không xác định`, or exact
  normalized category `error`.
- Record one rejection event per newly rejected lesson.

Before applying a rejection, the repair must confirm the lesson still has the
status and defect marker captured by the audit. A changed row is skipped and
reported as a precondition failure.

### 6.2 Review-only findings

- Approved lessons without evidence.
- Incomplete or vague content not matched by deterministic rules.
- Sources that require network access or interpretation.
- Conflicting lifecycle history.
- Legacy JSON drift.
- Failed jobs that may require source replay.

### 6.3 Forbidden repairs

- Delete lessons, sources, evidence, events, or backups.
- Create evidence, provenance, or lesson content.
- Approve pending lessons.
- Copy lifecycle state from legacy JSON into SQLite.
- Call an LLM or external provider.
- Continue after backup verification fails.

## 7. Failure Handling and Recovery

- Failure before repair leaves the live database unchanged.
- Repair actions run in an immediate SQLite transaction. Any repair exception
  rolls back the complete repair transaction.
- A failed post-check does not overwrite the database from backup
  automatically. It leaves the bot and worker stopped and reports
  `manual_intervention_required`.
- Backups are immutable and are never automatically deleted.
- Runtime restart is allowed only after database integrity, foreign keys,
  lifecycle invariants, and FTS consistency pass.
- If one runtime process restarts and the other fails, stop the restarted
  process and report a failed maintenance result rather than leaving a partial
  runtime.

## 8. Reporting and Privacy

Reports include:

- Run identifier and timestamps.
- Database and backup paths.
- Schema version and aggregate counts.
- Finding identifiers and severities.
- Planned and applied action identifiers.
- Before/after statuses and hashes where appropriate.
- Verification results.
- Process stop/start outcomes.

Reports must not contain lesson bodies, evidence excerpts, private source URLs,
Telegram identifiers, credentials, cookies, tokens, or environment values.

## 9. Testing Strategy

### 9.1 KnowledgeLifecycle tests

- Owner isolation for every state-changing operation.
- Allowed and forbidden transitions.
- Approval refusal for `needs_reanalysis`.
- Idempotent repeated approve and reject.
- One event per effective transition.
- FTS inclusion for approved lessons and removal for rejected lessons.
- Consistent duplicate policy across command, callback, and batch callers.

### 9.2 DataHealth tests

- `audit()` performs no writes.
- Detection of missing, extra, orphaned, and mismatched FTS rows.
- Detection of unambiguous and ambiguous missing approval timestamps.
- Detection of each deterministic defective-lesson rule.
- Safe repair precondition checks.
- Transaction rollback when any repair action fails.
- Idempotent second repair run.

### 9.3 MaintenanceRunner tests

- Clean successful maintenance run against a temporary database.
- Ambiguous or missing runtime process state.
- Process shutdown timeout.
- Backup creation and verification failure.
- Repair failure.
- Post-check failure.
- Partial restart failure.
- Redaction of report content.

Tests use temporary databases and fake process adapters. They do not stop the
live runtime.

## 10. Production Verification

Before maintenance:

- Run focused lifecycle, database, backup, Telegram, and worker tests.
- Resolve the current hanging full-suite behavior.
- Confirm the expected bot and worker entrypoints.

During maintenance:

- Create and verify a backup containing all lessons present at shutdown.
- Save the pre-repair audit and repair plan.
- Apply safe repair actions once.
- Run all required post-checks.

After maintenance:

- Confirm defective lessons are rejected and retained.
- Confirm FTS contains exactly approved lessons.
- Confirm database integrity and zero foreign-key violations.
- Confirm bot and worker restart and remain healthy.
- Run a Telegram read-only smoke check and one temporary-database lifecycle
  write test.
- Verify the maintenance report contains no sensitive content.

## 11. Completion Criteria

This phase is complete when:

- A current, verified backup contains the complete live lesson set.
- All production approval, rejection, and re-analysis entrypoints use
  `KnowledgeLifecycle`.
- Deterministically defective lessons are rejected, retained, and audited.
- FTS exactly matches approved lessons.
- Database integrity and foreign-key checks pass.
- Focused tests pass and the full test suite no longer hangs.
- The Telegram bot and worker restart successfully after maintenance.
- A redacted before/after maintenance report and an operator recovery runbook
  exist.

## 12. Deferred Work

The following work requires separate designs and implementation plans:

- Re-analysis of rejected lessons with an LLM.
- Obsidian event projection.
- Explicit and automatic correction memory.
- Hybrid semantic retrieval.
- Unified media acquisition and crawler reliability.
- Full migration from `telegram_bot.py` to `apps/telegram/`.

