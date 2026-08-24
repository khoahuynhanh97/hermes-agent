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
Review and verify Phase 5 Task 5 Idempotency & Correlation Remediation (`7e5f819b0c`), then accept Task 5 and authorize Phase 5 Task 6 (Inventory And Reconcile Legacy Data Without Deletion).

Scope:
- Verify `hermes_personal/product_video/handlers.py`, `hermes_personal/integrations/product_intelligence/client.py`, `hermes_personal/integrations/video_factory/client.py`, and `tests/hermes_personal/product_video/test_handlers.py`.
- Run verification tests, ruff, and git diff check.
- Accept Task 5 and authorize Phase 5 Task 6 for Worker.

---

## Last Worker Report

Iteration: 47
Phase: Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

Implemented:
- Propagated `workflow_id`, `job_id`, and `idempotency_key` correlation metadata from all 8 product-to-video handlers to injected `ProductIntelligenceClient` and `VideoFactoryClient` methods.
- Updated `ProductIntelligenceClient` and `VideoFactoryClient` signatures and wrapper payloads to embed correlation metadata.
- Added comprehensive unit tests in `test_handlers.py` proving:
  * Injected PI and VF clients receive exact `workflow_id`, `job_id`, and `idempotency_key` correlation arguments.
  * Idempotent replay with matching `idempotency_key` returns the cached/replayed artifact without triggering duplicate paid/client side-effects.
  * Budget reservation occurs before paid client invocations and is safely released on post-reservation failure.
- Verified all 33 tests in `test_handlers.py` and `test_job_handlers.py`, 43 tests in `product_video` suite, and 177 tests in total repo suite.

Files Changed:
- `hermes_personal/integrations/product_intelligence/client.py`
- `hermes_personal/integrations/video_factory/client.py`
- `hermes_personal/product_video/handlers.py`
- `tests/hermes_personal/product_video/test_handlers.py`

Commit: `7e5f819b0c` (`feat(product_video): propagate correlation metadata to clients and guarantee no duplicate paid effects on idempotent replay`)

Verification:
- `uv run pytest tests/hermes_personal/product_video/test_handlers.py tests/hermes_personal/product_video/test_job_handlers.py -q` -> 33 passed
- `uv run pytest tests/hermes_personal/product_video tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 177 passed
- `uv run ruff check hermes_personal/product_video hermes_personal/integrations tests/hermes_personal/product_video` -> All checks passed!
- `git diff --check b5a1b09ccd..HEAD` -> Clean

Remaining Issues:
- None.

Risks/Blockers:
- None.

---

## Last Planner Review

Iteration: 47

Decision:
REWORK Phase 5 Task 5 strict remediation (`f34afbaa11`) before authorizing Task 6.

Assessment:
- Reviewed Worker Report Iteration 46 and commit `f34afbaa11` against Gate 5 Task 5 in `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`.
- Independent verification passed: `uv run pytest tests/hermes_personal/product_video/test_handlers.py tests/hermes_personal/product_video/test_job_handlers.py -q` -> 32 passed; `uv run pytest tests/hermes_personal/product_video tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 176 passed; `uv run ruff check hermes_personal/product_video hermes_personal/integrations tests/hermes_personal/product_video` -> passed; `git diff --check b5a1b09ccd..HEAD` -> clean.
- The remediation fixed the previous private `_cache`/ctx-state shortcut and added ref/digest/HITL/terminal-dispatch coverage, but it still falls short of the Task 5 contract for workflow/job/idempotency correlation and duplicate paid-effect protection.

Findings / Evidence:
- `hermes_personal/product_video/handlers.py:162`-`199` calls Product Intelligence methods without passing `ctx.workflow_id`, `ctx.job_id`, or `ctx.idempotency_key`; `JobContext.idempotency_key` is defined at line 51 but is not used by any handler.
- `hermes_personal/product_video/handlers.py:201`-`289` passes only the immediate stage input (`brief_config`, `brief_ref`, `scene_ref`, `story_ref`, `render_ref`) to Video Factory methods. It does not pass workflow/job/idempotency correlation even though Gate 5 Task 5 requires workflow/job/idempotency ownership before paid/provider effects.
- `hermes_personal/integrations/video_factory/client.py:49`-`67` accepts `**kwargs` but ignores those arguments and still returns deterministic local payloads, so tests cannot prove provider-bound correlation or idempotency propagation.
- `tests/hermes_personal/product_video/test_job_handlers.py:160`-`166` labels idempotency as deterministic artifact equality while directly invoking the client twice; it does not prove duplicate dispatch/retry avoids a second paid/client effect.
- `tests/hermes_personal/product_video/test_handlers.py:155`-`167` proves only a single forwarded ref for one VF stage and explicitly asserts `create_scene_plan("brief_ref_123")`; it would fail to catch missing workflow/job/idempotency metadata across the eight handlers.
- Budget coverage still asserts failure/release behavior only indirectly. There is no test proving reservation happens before the client call for each paid stage or that actual cost/idempotent replay is recorded/released consistently at the handler boundary.

Plan Adjustment:
- Reason: Worker addressed earlier state/ref gaps but interpreted idempotency as deterministic fake output instead of a no-duplicate-effect contract propagated to injected provider clients.
- Impact: Task 6 reconciliation should not build on handlers that may duplicate paid effects or lose correlation between durable jobs and external PI/VF artifacts.
- Affected phases/tasks: Phase 5 Task 5 only; Task 6 remains blocked until Task 5 is accepted.
- Proposed correction: Add failing tests around PI/VF client call signatures, idempotent replay/retry, and budget-before-client order, then minimally update handlers/client adapters to satisfy them.

Reviewed Worker Iteration: 46
Reviewed Commit/Range: `f34afbaa11` / `cf5e558c30..f34afbaa11` (coordination handoff at `5a03ba0fa6`)

Next Step:
Worker to remediate the remaining Phase 5 Task 5 idempotency/correlation gaps, then report Iteration 47 back to PLANNER.
---

## History

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
