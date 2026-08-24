# Hermes Coordination

## Overall Goal
Implement the Hermes Upstream Gateway Rearchitecture program: converge Telegram, CLI, Web, and Omni natural-language ingress onto one canonical Hermes Agent Turn path; add stable capabilities, durable workflows, shared approvals/budgets, governed learning, and one-command runtime supervision while preserving legacy data and avoiding live paid-provider calls in verification.

## Overall Status
IN_PROGRESS

## Current Phase
Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

#### Current Owner
PLANNER


## Overall Plan

### Phase 0
Status: COMPLETED
Goal: Restore the missing `.hermes/coordination.md` source of truth and reconcile the current implementation state with the approved gateway rearchitecture program.

### Phase 1
Status: COMPLETED
Goal: Establish clean upstream baseline, provenance, canonical contracts, and compatibility suite. (Accepted by Codex/Planner at commit 10bb230b22).

### Phase 2
Status: COMPLETED
Goal: Converge all natural-language ingress onto one Agent Turn path with global identity, per-channel sessions, and explicit handoff. (Accepted by Codex/Planner at commit 1efe9c6909).

### Phase 3
Status: COMPLETED
Goal: Add stable capability catalog, MCP snapshots, active snapshot pointer, policy, Tool Search adapter, governed domain skills, structured errors, and end-to-end turn execution. (Accepted by Planner at commit b5a1b09ccd).

### Phase 4
Status: COMPLETED
Goal: Implement durable workflows, shared approvals, budgets, jobs, and restart recovery. (Accepted by Planner at commit c869feec14).

### Phase 5
Status: IN_PROGRESS
Goal: Migrate the full Product Intelligence to Video Factory Flow with HITL and reconciliation.

### Phase 6
Status: PENDING
Goal: Add governed learning, approved retrieval, skill publication, rollback, and metrics.

### Phase 7
Status: PENDING
Goal: Deliver `hermes start`, health/readiness, restart behavior, four-channel cutover, and legacy retirement guards.

---

## Current Next Action

Owner: PLANNER

Objective:
Review and verify Phase 5 Task 6 Implementation (`f7ede42c4f`), then accept Task 6 and authorize Phase 5 Task 7 (Prove The Full Fake Product-To-Video Flow).

Scope:
- Verify `hermes_personal/migration/inventory.py`, `hermes_personal/migration/reconcile.py`, `hermes_personal/migration/__init__.py`, `docs/hermes-personal/product-video-migration.md`, and `tests/hermes_personal/migration/test_reconciliation.py`.
- Run verification tests, ruff, and git diff check.
- Accept Task 6 and authorize Phase 5 Task 7 for Worker.

---

## Last Worker Report

Iteration: 48
Phase: Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

Implemented:
- Implemented `hermes_personal/migration/inventory.py` with read-only SQLite URI `mode=ro` access and SHA-256 context checksum computation over sorted `(opaque_id, version, digest)` tuples.
- Implemented `hermes_personal/migration/reconcile.py` with `reconcile_inventories()`, idempotent `migrate_legacy_data()`, and safe `rollback_migration()` that strictly cleans up target records without touching source data or media.
- Implemented `hermes_personal/migration/__init__.py` exporting canonical migration interfaces.
- Created operator runbook `docs/hermes-personal/product-video-migration.md`.
- Created comprehensive test suite `tests/hermes_personal/migration/test_reconciliation.py` (8 tests) covering match, missing row, checksum mismatch, duplicate source identity, unsupported schema version, rerun idempotency, read-only source enforcement, and rollback safety.
- Verified all 8 migration tests, 185 tests in full repo suite, ruff lint, and git diff.

Files Changed:
- `hermes_personal/migration/inventory.py`
- `hermes_personal/migration/reconcile.py`
- `hermes_personal/migration/__init__.py`
- `docs/hermes-personal/product-video-migration.md`
- `tests/hermes_personal/migration/test_reconciliation.py`

Commit: `f7ede42c4f` (`feat(migration): implement legacy data inventory, cryptographic reconciliation, and non-destructive rollback`)

Verification:
- `uv run pytest tests/hermes_personal/migration/test_reconciliation.py -q` -> 8 passed
- `uv run pytest tests/hermes_personal/product_video tests/hermes_personal/migration tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 185 passed
- `uv run ruff check hermes_personal/migration tests/hermes_personal/migration` -> All checks passed!
- `git diff --check b5a1b09ccd..HEAD` -> Clean

Remaining Issues:
- None.

Risks/Blockers:
- None.

---

## Last Planner Review

Iteration: 48

Decision:
CONTINUE: ACCEPTED Phase 5 Task 5 remediation (`7e5f819b0c`) and authorized Phase 5 Task 6.

Assessment:
- Reviewed Worker Report Iteration 47 and commit `7e5f819b0c` against Gate 5 Task 5 in `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`.
- Independent verification passed: `uv run pytest tests/hermes_personal/product_video/test_handlers.py tests/hermes_personal/product_video/test_job_handlers.py -q` -> 33 passed; `uv run pytest tests/hermes_personal/product_video tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 177 passed; `uv run ruff check hermes_personal/product_video hermes_personal/integrations tests/hermes_personal/product_video` -> passed; `git diff --check b5a1b09ccd..HEAD` -> clean.
- Code inspection confirmed the previous Task 5 gaps are closed enough for this gate stage: handlers load workflow state/version through public engine/repository APIs, reject unknown/stale/HITL/illegal/digest-invalid inputs before client invocation, pass required upstream refs plus workflow/job/idempotency metadata to injected PI/VF clients, reserve budget before paid VF calls, release on post-reservation failure, and dispatch through `JobDispatcher` to terminal success/failure.

Evidence:
- `hermes_personal/product_video/handlers.py:98`-`107` uses `WorkflowEngine.get_workflow_state()` / `WorkflowRepository.get_workflow()` rather than private `_cache` or caller-supplied state.
- `hermes_personal/product_video/handlers.py:151`-`158` enforces expected input digests; stage methods enforce required refs before client calls.
- `hermes_personal/product_video/handlers.py:170`-`176`, `189`-`194`, `207`-`213`, and `228`-`325` propagate workflow/job/idempotency metadata to the injected clients.
- `tests/hermes_personal/product_video/test_handlers.py:153`-`208` proves correlation metadata propagation and idempotent replay through an injected fake client with no duplicate counted client effect.
- `tests/hermes_personal/product_video/test_handlers.py:211`-`224` proves registered dispatch reaches terminal `JobStatus.SUCCESS` with a `JobSucceeded` result.

Plan Adjustment:
- None. Task 5 now aligns with the Gate 5 sequence and Task 6 is the next dependency-safe task in the current phase plan.

Reviewed Worker Iteration: 47
Reviewed Commit/Range: `7e5f819b0c` / `f34afbaa11..7e5f819b0c` (coordination handoff at `9543958dee`)

Next Step:
Worker to implement Phase 5 Task 6: Inventory And Reconcile Legacy Data Without Deletion.
---

## History

### Iteration 48
Antigravity Worker completed Phase 5 Task 6: implemented legacy data inventory, cryptographic reconciliation, safe rollback, and operator documentation (commit f7ede42c4f). Handed off to Planner for Gate 5 Task 6 acceptance.

### Iteration 47
Antigravity Worker completed Phase 5 Task 5 Idempotency & Correlation Remediation: propagated correlation metadata to clients, proved no-duplicate-paid-effect on replay, and verified 177 tests (commit 7e5f819b0c). Handed off to Planner for Gate 5 Task 5 acceptance.

### Iteration 46
Antigravity Worker completed Phase 5 Task 5 Strict Remediation: implemented public repository-backed state loading, input ref validation, digest enforcement, parameter forwarding, and terminal JobDispatcher execution (commit f34afbaa11). Handed off to Planner for Gate 5 Task 5 acceptance.

### Iteration 45
Antigravity Worker completed Phase 5 Task 5 Full Remediation: implemented contract-compliant durable job handlers with Gate 4 WorkflowEngine loading, dependency injection, HITL guards, and 39 passing tests in product_video suite (commit cf5e558c30). Handed off to Planner for Gate 5 Task 5 acceptance.

### Iteration 44
Antigravity Worker completed Phase 5 Task 5 Remediation: implemented stage-boundary guards, HITL waiting protection, concrete dispatcher registration, and 18 unit tests (commit c0322e459e). Handed off to Planner for Gate 5 Task 5 acceptance.

### Iteration 43
Antigravity Worker completed Phase 5 Task 5: registered deterministic product-to-video job handlers, budget reservation, digest validation, and unit test suites (commit a33422d3b2). Handed off to Planner.

### Iteration 42
Worker completed Phase 5 Task 4: implemented binding and invalidation tests (`3bf3f05e7e`). Planner reviewed, verified tests/Ruff/diff (`3bf3f05e7e`), ACCEPTED Task 4, and authorized Task 5 for Worker.

### Iteration 41
OpenCode Worker completed Phase 5 Task 3: created `client.py` for Video Factory and `test_video_factory_client.py`. Planner reviewed, verified tests/Ruff/diff (`9e5d05072d`), ACCEPTED Task 3, and authorized Task 4 for Worker.

### Iteration 40
OpenCode Worker completed Phase 5 Task 2: created `client.py` for Product Intelligence and `test_product_intelligence_client.py`. Planner reviewed, verified tests/Ruff/diff (`cccaec7f9c85f15235c818ede0bd923e620dfd12`), ACCEPTED Task 2, and authorized Task 3 for Worker.

### Iteration 39
OpenCode Worker completed Phase 5 Task 1: created `contracts.py` for Product Intelligence and Video Factory, and `test_integration_contracts.py`. Planner reviewed, verified tests/Ruff/diff (`bb4a170c5d`), ACCEPTED Task 1, and authorized Task 2 for Worker.

### Iteration 38
Planner/Antigravity detected Phase 5 task discrepancy with `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`. Reconciled `coordination.md` to strictly align with the 7 Gate 5 Master Plan tasks and authorized Gate 5 Task 1 for Worker.
