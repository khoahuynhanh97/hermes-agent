# Hermes Coordination

## Overall Goal
Implement the Hermes Upstream Gateway Rearchitecture program: converge Telegram, CLI, Web, and Omni natural-language ingress onto one canonical Hermes Agent Turn path; add stable capabilities, durable workflows, shared approvals/budgets, governed learning, and one-command runtime supervision while preserving legacy data and avoiding live paid-provider calls in verification.

## Overall Status
IN_PROGRESS

## Current Phase
Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

## Current Owner
WORKER


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

Owner: WORKER

Objective:
Implement Phase 5 Task 5: Register Deterministic Product-To-Video Job Handlers (per Gate 5 Master Plan `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`).

Scope:
- Create `hermes_personal/integrations/product_video/handlers.py` (`register_product_video_job_handlers()`, handlers for `product_video.creative_brief`, `product_video.scene_plan`, `product_video.storyboard`, `product_video.render`, `product_video.export`).
- Create `tests/hermes_personal/product_video/test_job_handlers.py` testing handler registration with Gate 4 JobEngine, execution of each job step, locked digest verification, budget forwarding, and idempotency without live paid-provider calls.
- Do not implement Task 6 yet. Do not call live providers or paid APIs.

Verification:
- `uv run pytest tests/hermes_personal/product_video/test_job_handlers.py -q`
- `uv run pytest tests/hermes_personal/product_video -q`
- `uv run pytest tests/hermes_personal/workflows tests/hermes_personal/capabilities -q`
- `uv run ruff check hermes_personal/integrations tests/hermes_personal/product_video`
- `git diff --check b5a1b09ccd..HEAD`

Handoff Rule:
After completing implementation, verification, and git commit, update `coordination.md`:
1. Record Last Worker Report (files changed, commit hash, test counts, commands run).
2. Append Iteration 43 to History.
3. Set `Current Next Action.Owner = PLANNER`.
4. Set `Current Owner = PLANNER`.
5. Save `coordination.md` and EXIT. Do not loop or wait.

---

## Last Worker Report

Iteration: 42
Phase: Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

Implemented:
- Created `hermes_personal/integrations/product_video/binding.py` (`ProductVideoBinding`, `ProductVideoBindingService`, `verify_binding_integrity()`).
- Created `tests/hermes_personal/product_video/test_binding_invalidation.py` testing binding creation, digest verification across video pipeline stages, and invalidation triggers.

Files Changed:
- `hermes_personal/integrations/product_video/binding.py`
- `tests/hermes_personal/product_video/test_binding_invalidation.py`

Commit: `3bf3f05e7e` (`feat(product_video): implement binding and invalidation tests`)

Verification:
- `uv run pytest tests/hermes_personal/product_video/test_binding_invalidation.py -q` -> 2 passed
- `uv run pytest tests/hermes_personal/product_video -q` -> 10 passed
- `uv run pytest tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 134 passed
- `uv run ruff check hermes_personal/integrations tests/hermes_personal/product_video` -> All checks passed!
- `git diff --check b5a1b09ccd..HEAD` -> Clean

Remaining Issues:
- None.

Risks/Blockers:
- None.

---

## Last Planner Review

Iteration: 42

Decision:
ACCEPTED TASK 4 COMPLETE (Implement Product-To-Video Binding And Invalidation Accepted at commit 3bf3f05e7e)

Assessment:
- Reviewed Phase 5 Task 4 implementation (`3bf3f05e7e`).
- Verified binding invalidation unit tests (`test_binding_invalidation.py`), 10 total `product_video` tests, 134 workflow & capability tests, Ruff cleanliness, and clean whitespace (`git diff --check b5a1b09ccd..HEAD`).
- Task 4 is COMPLETED and ACCEPTED. Phase 5 Task 5 is authorized per Gate 5 Master Plan (`docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`).

Plan Adjustment:
- Authorized Phase 5 Task 5: Register Deterministic Product-To-Video Job Handlers (`hermes_personal/integrations/product_video/handlers.py`).

Next Step:
Worker to implement Phase 5 Task 5 (`hermes_personal/integrations/product_video/handlers.py` & `tests/hermes_personal/product_video/test_job_handlers.py`).

---

## History

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
