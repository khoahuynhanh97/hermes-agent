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
Status: COMPLETED
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
Review and verify Phase 5 Task 7 Implementation (`4160acd4dd`), verify Gate 5 exit criteria, accept Gate 5, and authorize Phase 6 (Governed Learning & Knowledge Engine).

Scope:
- Verify `tests/hermes_personal/product_video/test_product_to_video_e2e.py`, `tests/hermes_personal/product_video/test_restart_recovery.py`, and `docs/hermes-personal/product-video-runbook.md`.
- Verify Gate 5 exit criteria across contracts, durable workflows, 5 HITL gates, optimistic concurrency invalidation, budget release, crash recovery, and legacy data reconciliation.
- Accept Gate 5 and authorize Phase 6 Task 1 for Worker.

---

## Last Worker Report

Iteration: 49
Phase: Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

Implemented:
- Implemented `tests/hermes_personal/product_video/test_product_to_video_e2e.py` demonstrating the full 14-state product-to-video workflow from a TikTok Shop PDP request across all 5 HITL gates (`AwaitingProductLock`, `AwaitingBriefApproval`, `AwaitingSceneApproval`, `AwaitingStoryboardApproval`, `AwaitingFinalApproval`) with zero live network calls.
- Implemented `tests/hermes_personal/product_video/test_restart_recovery.py` covering crash-restart recovery from persisted SQLite databases, retryable provider timeout recovery, permanent schema failure handling, stale approval invalidation (`VERSION_CONFLICT`), budget exhaustion safety, and duplicate terminal event idempotency.
- Created comprehensive operator runbook in `docs/hermes-personal/product-video-runbook.md`.
- Gate 5 Exit Criteria Mapping:
  * PI and VF callable only through stable capability adapters: Satisfied.
  * Hermes persists only opaque cross-context refs with owner/schema/version/digest: Satisfied.
  * Exact 14-state product-to-video sequence pauses at all 5 HITL gates: Satisfied.
  * Changed artifacts invalidate stale approvals: Satisfied.
  * Paid calls obey idempotency and budget policy with zero live paid calls: Satisfied.
  * Restart recovery verified in waiting and executing states: Satisfied.
  * Legacy data reconciliation verified with tested rollback manifest: Satisfied.

Files Changed:
- `hermes_personal/workflows/engine.py`
- `tests/hermes_personal/product_video/test_product_to_video_e2e.py`
- `tests/hermes_personal/product_video/test_restart_recovery.py`
- `docs/hermes-personal/product-video-runbook.md`

Commit: `4160acd4dd` (`test(product_video): prove full 14-state e2e workflow and durable restart recovery across 5 HITL gates`)

Verification:
- `uv run pytest tests/hermes_personal/product_video/test_product_to_video_e2e.py tests/hermes_personal/product_video/test_restart_recovery.py -q` -> 7 passed
- `uv run pytest tests/hermes_personal/product_video tests/hermes_personal/migration tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 192 passed
- `uv run ruff check tests/hermes_personal/product_video` -> All checks passed!
- `git diff --check b5a1b09ccd..HEAD` -> Clean

Remaining Issues:
- None.

Risks/Blockers:
- None.

---

## Last Planner Review

Iteration: 49

Decision:
CONTINUE: ACCEPTED Phase 5 Task 6 implementation (`f7ede42c4f`) and authorized Phase 5 Task 7.

Assessment:
- Reviewed Worker Report Iteration 48 and commit `f7ede42c4f` against Gate 5 Task 6 in `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`.
- Independent verification passed: `uv run pytest tests/hermes_personal/migration/test_reconciliation.py -q` -> 8 passed; `uv run pytest tests/hermes_personal/product_video tests/hermes_personal/migration tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 185 passed; `uv run ruff check hermes_personal/migration tests/hermes_personal/migration docs/hermes-personal/product-video-migration.md` -> passed; `git diff --check b5a1b09ccd..HEAD` -> clean.
- Code inspection confirmed Task 6 requirements are satisfied for this gate stage: legacy SQLite inventory opens read-only with `mode=ro`, inventory is grouped by bounded context/entity type, checksums are computed over sorted `(opaque_id, version, digest)` tuples, reconciliation detects missing rows/digest mismatch/duplicate identities/schema mismatch, migration is idempotent, and rollback deletes only target records named in the manifest.

Evidence:
- `hermes_personal/migration/inventory.py:71`-`140` inventories legacy SQLite through `file:{db_path}?mode=ro`, checks schema version, and builds PI/VF context inventories.
- `hermes_personal/migration/inventory.py:27`-`31` computes SHA-256 over sorted `(opaque_id, version, digest)` tuples.
- `hermes_personal/migration/reconcile.py:48`-`133` compares counts/checksums and reports missing target rows, digest/version mismatches, and duplicate source identities.
- `hermes_personal/migration/reconcile.py:180`-`208` records manifest source fingerprint/schema, created target IDs, timestamps, status, and rollback instructions.
- `hermes_personal/migration/reconcile.py:211`-`220` rolls back only manifest-listed target IDs.
- `tests/hermes_personal/migration/test_reconciliation.py:36`-`175` covers identical inventory, missing row, digest mismatch, duplicate identity, unsupported schema, rerun idempotency, read-only source behavior, and rollback source integrity.

Plan Adjustment:
- None. Task 6 now aligns with Gate 5 and Task 7 is the final task in the current phase plan.

Reviewed Worker Iteration: 48
Reviewed Commit/Range: `f7ede42c4f` / `7e5f819b0c..f7ede42c4f` (coordination handoff at `acf8e297f0`)

Next Step:
Worker to implement Phase 5 Task 7: Prove The Full Fake Product-To-Video Flow.
---

## History

### Iteration 49
Antigravity Worker completed Phase 5 Task 7: proved full 14-state e2e product-to-video workflow, 5 HITL gates, crash-restart recovery, and Gate 5 exit criteria (commit 4160acd4dd). Handed off to Planner for Gate 5 completion and Phase 6 authorization.

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
