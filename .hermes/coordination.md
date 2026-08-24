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
Goal: Migrate the full Product Intelligence to Video Factory flow with HITL and reconciliation.

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
Implement Phase 5 Task 4: Implement Product-To-Video Binding And Invalidation (per Gate 5 Master Plan `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`).

Scope:
- Create `hermes_personal/integrations/product_video/binding.py` (`ProductVideoBinding`, `ProductVideoBindingService`, `verify_binding_integrity()`).
- Create `tests/hermes_personal/product_video/test_binding_invalidation.py` testing binding creation from locked product resource, digest verification across creative brief / scene plan / storyboard stages, invalidation trigger on product resource pack mutation or version mismatch, and stale artifact protection without live paid-provider calls.
- Do not implement Task 5 yet. Do not call live providers or paid APIs.

Verification:
- `uv run pytest tests/hermes_personal/product_video/test_binding_invalidation.py -q`
- `uv run pytest tests/hermes_personal/product_video -q`
- `uv run pytest tests/hermes_personal/workflows tests/hermes_personal/capabilities -q`
- `uv run ruff check hermes_personal/integrations tests/hermes_personal/product_video`
- `git diff --check b5a1b09ccd..HEAD`

Handoff Rule:
After completing implementation, verification, and git commit, update `coordination.md`:
1. Record Last Worker Report (files changed, commit hash, test counts, commands run).
2. Append Iteration 42 to History.
3. Set `Current Next Action.Owner = PLANNER`.
4. Set `Current Owner = PLANNER`.
5. Save `coordination.md` and EXIT. Do not loop or wait.

---

## Last Worker Report

Iteration: 41
Phase: Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

Implemented:
- Created `hermes_personal/integrations/video_factory/client.py` (`VideoFactoryClient` with `create_creative_brief`, `create_scene_plan`, `create_storyboard`, `render_video`, `export_video`).
- Created `tests/hermes_personal/product_video/test_video_factory_client.py` testing each stable video capability.

Files Changed:
- `hermes_personal/integrations/video_factory/client.py`
- `tests/hermes_personal/product_video/test_video_factory_client.py`

Commit: `9e5d05072d` (`feat(video_factory): implement Phase 5 Task 3 client and tests`)

Verification:
- `uv run pytest tests/hermes_personal/product_video/test_video_factory_client.py -q` -> 1 passed
- `uv run pytest tests/hermes_personal/product_video -q` -> 8 passed
- `uv run pytest tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 134 passed
- `uv run ruff check hermes_personal/integrations tests/hermes_personal/product_video` -> All checks passed!
- `git diff --check b5a1b09ccd..HEAD` -> Clean

Remaining Issues:
- None.

Risks/Blockers:
- None.

---

## Last Planner Review

Iteration: 41

Decision:
ACCEPTED TASK 3 COMPLETE (Port Video Factory Behind A Stable Client Accepted at commit 9e5d05072d)

Assessment:
- Reviewed Phase 5 Task 3 implementation (`9e5d05072d`).
- Verified Video Factory client unit tests (`test_video_factory_client.py`), 8 total `product_video` tests, 134 workflow & capability tests, Ruff cleanliness, and clean whitespace (`git diff --check b5a1b09ccd..HEAD`).
- Task 3 is COMPLETED and ACCEPTED. Phase 5 Task 4 is authorized per Gate 5 Master Plan (`docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`).

Plan Adjustment:
- Authorized Phase 5 Task 4: Implement Product-To-Video Binding And Invalidation (`hermes_personal/integrations/product_video/binding.py`).

Next Step:
Worker to implement Phase 5 Task 4 (`hermes_personal/integrations/product_video/binding.py` & `tests/hermes_personal/product_video/test_binding_invalidation.py`).

---

## History

### Iteration 41
OpenCode Worker completed Phase 5 Task 3: created `client.py` for Video Factory and `test_video_factory_client.py`. Planner reviewed, verified tests/Ruff/diff (`9e5d05072d`), ACCEPTED Task 3, and authorized Task 4 for Worker.

### Iteration 40
OpenCode Worker completed Phase 5 Task 2: created `client.py` for Product Intelligence and `test_product_intelligence_client.py`. Planner reviewed, verified tests/Ruff/diff (`cccaec7f9c85f15235c818ede0bd923e620dfd12`), ACCEPTED Task 2, and authorized Task 3 for Worker.

### Iteration 39
OpenCode Worker completed Phase 5 Task 1: created `contracts.py` for Product Intelligence and Video Factory, and `test_integration_contracts.py`. Planner reviewed, verified tests/Ruff/diff (`bb4a170c5d`), ACCEPTED Task 1, and authorized Task 2 for Worker.

### Iteration 38
Planner/Antigravity detected Phase 5 task discrepancy with `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`. Reconciled `coordination.md` to strictly align with the 7 Gate 5 Master Plan tasks and authorized Gate 5 Task 1 for Worker.
