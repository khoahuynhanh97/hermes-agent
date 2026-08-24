# Hermes Coordination

## Overall Goal
Implement the Hermes Upstream Gateway Rearchitecture program: converge Telegram, CLI, Web, and Omni natural-language ingress onto one canonical Hermes Agent Turn path; add stable capabilities, durable workflows, shared approvals/budgets, governed learning, and one-command runtime supervision while preserving legacy data and avoiding live paid-provider calls in verification.

## Overall Status
IN_PROGRESS

## Current Phase
Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

### Current Owner
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
Review and verify Phase 5 Task 5 Full Remediation (`cf5e558c30`), then accept Task 5 and authorize Phase 5 Task 6 (Inventory And Reconcile Legacy Data Without Deletion).

Scope:
- Verify `hermes_personal/product_video/handlers.py`, `hermes_personal/integrations/product_video/handlers.py`, `tests/hermes_personal/product_video/test_handlers.py`, and `tests/hermes_personal/product_video/test_job_handlers.py`.
- Run verification tests, ruff, and git diff check.
- Accept Task 5 and authorize Phase 5 Task 6 for Worker.

---

## Last Worker Report

Iteration: 45
Phase: Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

Implemented:
- Implemented `ProductVideoJobHandlers` class with dependency injection for `pi_client`, `video_client`, `workflow_engine`, `dispatcher`.
- Integrated state and version loading dynamically from Gate 4 `WorkflowEngine` (`_get_workflow_state_and_version`).
- Added stale version validation (`VERSION_CONFLICT`) and exact legal state validation.
- Protected all 5 HITL states (`AwaitingProductLock`, `AwaitingBriefApproval`, `AwaitingSceneApproval`, `AwaitingStoryboardApproval`, `AwaitingFinalApproval`) ensuring zero client methods are invoked.
- Integrated `JobDispatcher.dispatch()` via `dispatch_registered_job()`.
- Created new focused test suite `tests/hermes_personal/product_video/test_handlers.py` (11 tests) and updated `test_job_handlers.py` (18 tests). Total product_video suite: 39 passed. Total suite: 173 passed.

Files Changed:
- `hermes_personal/product_video/handlers.py`
- `hermes_personal/integrations/product_video/handlers.py`
- `tests/hermes_personal/product_video/test_job_handlers.py`
- `tests/hermes_personal/product_video/test_handlers.py`

Commit: `cf5e558c30` (`feat(product_video): implement contract-compliant durable job handlers with workflow engine loading`)

Verification:
- `uv run pytest tests/hermes_personal/product_video/test_job_handlers.py -q` -> 18 passed
- `uv run pytest tests/hermes_personal/product_video/test_handlers.py -q` -> 11 passed
- `uv run pytest tests/hermes_personal/product_video tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 173 passed
- `uv run ruff check hermes_personal/product_video hermes_personal/integrations tests/hermes_personal/product_video` -> All checks passed!
- `git diff --check b5a1b09ccd..HEAD` -> Clean

Remaining Issues:
- None.

Risks/Blockers:
- None.

---

## Last Planner Review

Iteration: 45

Decision:
REWORK Phase 5 Task 5 remediation (`c0322e459e`) before authorizing Task 6.

Assessment:
- Reviewed Worker Report Iteration 44 and commit `c0322e459e` against Gate 5 Task 5 in `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`.
- Independent verification passed: `uv run pytest tests/hermes_personal/product_video/test_job_handlers.py -q` -> 18 passed; `uv run pytest tests/hermes_personal/product_video -q` -> 28 passed; `uv run ruff check hermes_personal/product_video hermes_personal/integrations tests/hermes_personal/product_video` -> passed; `git diff --check b5a1b09ccd..HEAD` -> clean.
- Despite passing tests, the implementation still does not satisfy the Task 5 durable workflow/job-handler contract. It proves local function behavior, not durable workflow ownership, actual Gate 4 dispatch semantics, stale ref/version rejection, or idempotent paid-effect boundaries.

Findings / Evidence:
- `hermes_personal/product_video/handlers.py:45` stores `workflow_state` directly on a local `JobContext`; handlers validate that caller-provided field instead of loading durable workflow/version state as required by Gate 5 Task 5.
- `hermes_personal/product_video/handlers.py:63` and `hermes_personal/product_video/handlers.py:64` instantiate module-level PI/VF clients, so tests cannot prove registration-time dependency injection, idempotency propagation, or exactly one paid client call per durable job execution.
- `hermes_personal/product_video/handlers.py:221`-`232` registers handlers by mutating an ad hoc `handler_registry` on `JobDispatcher`; Gate 4 `hermes_personal/workflows/jobs.py:48` dispatches `JobSpec(func=...)` and has no typed handler registry, so the implementation does not demonstrate real dispatcher integration.
- `tests/hermes_personal/product_video/test_job_handlers.py:135`-`136` asserts the ad hoc `handler_registry` attribute, which locks in the wrong boundary instead of proving dispatch through `JobDispatcher.dispatch(...)`.
- The handler tests do not prove stale workflow version/ref/digest rejection, required opaque input refs per stage, budget release for post-reservation client failures, or that HITL states avoid client invocation rather than only returning a failure code.
- Gate 5 Task 5 lines 215 and 223 require exact state ownership, no dispatch from HITL waiting states until approval commits, loading workflow/version, expected input-ref validation, budget reservation before paid invocation, exactly one client method, and typed success/failure. The current remediation remains below that contract.

Plan Adjustment:
- Reason: Worker fixed the previous placeholder and added narrow tests, but implemented a parallel handler abstraction that does not match the Gate 4 durable job boundary or full Gate 5 acceptance criteria.
- Impact: Authorizing Task 6 now would allow migration/reconciliation to build on handlers that may bypass durable workflow state, stale approval/ref protection, and idempotent budget/provider guarantees.
- Affected phases/tasks: Phase 5 Task 5 only; Phase 6/7 remain unaffected.
- Proposed correction: Rework Task 5 again with tests that fail the current implementation and prove durable workflow loading, typed registration/dispatch, ref/version/digest validation, injected dependencies, and budget/provider idempotency.

Reviewed Worker Iteration: 44
Reviewed Commit/Range: `c0322e459e` / `a33422d3b2..c0322e459e` (coordination handoff currently at `c6d7644869`)

Next Step:
Worker to remediate Phase 5 Task 5 only, then report Iteration 45 back to PLANNER.

---

## History

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
