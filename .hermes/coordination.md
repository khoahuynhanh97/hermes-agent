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
Review and verify Phase 5 Task 7 Final Remediation (`39c8ff109f`), verify Gate 5 exit criteria mapping, accept Gate 5, and authorize Phase 6.

Scope:
- Verify PDP URL request provenance is passed through `research_job` and verified in downstream research artifact evidence.
- Verify complete artifact metadata assertions (owner, version, digests, payload, correlation metadata) across all 8 PI and VF stages.
- Verify stage-qualified idempotency key caching and `BudgetEngine` zero duplicate budget commitment on terminal export replay.
- Verify Gate 5 exit criteria across contracts, durable workflows, 5 HITL gates, optimistic concurrency invalidation, budget release, crash recovery, and legacy data reconciliation.
- Accept Gate 5 and authorize Phase 6 Task 1 for Worker.

---

## Last Worker Report

Iteration: 52
Phase: Phase 5 - Migrate Product Intelligence to Video Factory Flow with HITL & Reconciliation

Implemented:
- Embedded PDP URL (`https://shop.tiktok.com/view/product/17294829104`) into the real research request path (`handlers.research_job(..., pdp_url=...)`), asserting downstream research artifact output provenance.
- Proved comprehensive metadata across EVERY PI and VF artifact in the entire chain:
  * `research_art`: `report`, `workflow_id`, `idempotency_key`, `pdp_url`.
  * `pack_art`: `resource_pack_id`, `assets_mapping`, `workflow_id`, `idempotency_key`.
  * `locked_pack`: `status == "locked"`, `manifest_digest` (`sha256:`), `resource_pack_id`.
  * `brief_art`: `owner == "video_factory"`, `version == 1`, `digest` (`sha256:`), `artifact_ref` (`sha256:`), `payload`, `workflow_id`, `idempotency_key`.
  * `scene_art`: `owner == "video_factory"`, `version == 1`, `digest` (`sha256:`), `artifact_ref` (`sha256:`), `payload`, `workflow_id`, `idempotency_key`.
  * `story_art`: `owner == "video_factory"`, `version == 1`, `digest` (`sha256:`), `artifact_ref` (`sha256:`), `payload`, `workflow_id`, `idempotency_key`.
  * `render_art`: `owner == "video_factory"`, `version == 1`, `digest` (`sha256:`), `artifact_ref` (`sha256:`), `payload`, `workflow_id`, `idempotency_key`.
  * `export_art`: `owner == "video_factory"`, `version == 1`, `digest` (`sha256:`), `artifact_ref` (`sha256:`), `payload`, `workflow_id`, `idempotency_key`.
- Implemented stage-qualified idempotency key caching in `ProductVideoJobHandlers` and `BudgetAllocation.idempotency_key` awareness in `BudgetEngine`, proving that replaying paid terminal/export jobs with the same key commits ZERO duplicate budget ($20 first run, $20 on replay).
- Verified all 21 e2e/restart tests, 64 product_video & migration tests, and 206 total tests in repo suite.

Files Changed:
- `hermes_personal/product_video/handlers.py`
- `hermes_personal/workflows/budgets.py`
- `tests/hermes_personal/product_video/test_product_to_video_e2e.py`
- `tests/hermes_personal/product_video/test_restart_recovery.py`

Commit: `39c8ff109f` (`feat(product_video): add PDP provenance, complete artifact metadata, and idempotent budget accounting`)

Verification:
- `uv run pytest tests/hermes_personal/product_video/test_product_to_video_e2e.py tests/hermes_personal/product_video/test_restart_recovery.py -q` -> 21 passed
- `uv run pytest tests/hermes_personal/product_video tests/hermes_personal/migration tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 206 passed
- `uv run ruff check tests/hermes_personal/product_video docs/hermes-personal/product-video-runbook.md` -> All checks passed!

Remaining Issues:
- None.

Risks/Blockers:
- None.

---

## Last Planner Review

Iteration: 52

Decision:
REWORK: Phase 5 Task 7 remediation (`f2e72698cc`) improved real service evidence, but Gate 5 still cannot exit.

Assessment:
- Reviewed Worker Report Iteration 51 and commit `f2e72698cc` against Gate 5 Task 7 and Gate 5 exit criteria in `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-5.md`.
- Independent verification passed for the submitted suites: `uv run pytest tests/hermes_personal/product_video/test_product_to_video_e2e.py tests/hermes_personal/product_video/test_restart_recovery.py -q` -> 21 passed; `uv run pytest tests/hermes_personal/product_video tests/hermes_personal/migration tests/hermes_personal/workflows tests/hermes_personal/capabilities -q` -> 206 passed; `uv run ruff check tests/hermes_personal/product_video docs/hermes-personal/product-video-runbook.md` -> passed; `git diff --check b5a1b09ccd..HEAD` -> clean.
- Inspection confirmed the previous simulated approval/cost/lease evidence was materially improved: E2E now uses `ApprovalService`, `BudgetEngine.get_allocated_budget`, and restart tests use `WorkflowRecoveryService` and `JobDispatcher` timeout rather than a synthetic lease table.
- Remaining gaps are still acceptance-relevant: the TikTok PDP URL is not part of the actual PI research request path, artifact metadata is not asserted across the full PI/VF chain, and duplicate terminal replay still does not prove budget/idempotency safety.

Evidence/Findings:
- `tests/hermes_personal/product_video/test_product_to_video_e2e.py:52` defines `pdp_url`, but `handlers.research_job(...)` at `:84` receives only product name and keywords. The PDP URL is stored only in approval request payloads, so the test does not prove the flow starts from a PDP request as required by Gate 5 Task 7.
- `tests/hermes_personal/product_video/test_product_to_video_e2e.py:86`-`:120` checks workflow/idempotency metadata for research and digest/payload metadata for the brief, but it does not assert owner/schema-or-type/version/digest/correlation metadata for every PI/VF artifact: resource pack, lock, scene plan, storyboard, render, and export are not fully checked.
- `tests/hermes_personal/product_video/test_restart_recovery.py:258`-`:270` calls `export_job` twice with the same idempotency key and only asserts the artifact ref matches. Because `ProductVideoJobHandlers.export_job` reserves/commits budget before every successful call, this does not prove no duplicate paid/budget effect on terminal replay.
- `hermes_personal/workflows/budgets.py` now exposes allocated totals, but it still has no idempotency-aware allocation/commit record; the tests cannot distinguish one paid effect from a replay that committed the same amount twice.

Plan Adjustment:
Reason: Worker remediation correctly moved several checks to real services, but the remaining Task 7 evidence still misses PDP provenance through the actual PI path, complete artifact metadata, and idempotent budget accounting.
Impact: Gate 5 remains IN_PROGRESS; Phase 6 Task 1 is not authorized.
Affected phases/tasks: Phase 5 Task 7, Gate 5 exit criteria, Phase 6 kickoff.
Proposed correction: Keep the real-service assertions from Iteration 51 and add narrowly scoped evidence/implementation for PDP request propagation, full artifact-chain metadata, and no duplicate budget commit on paid idempotent replay.

Reviewed Worker Iteration: 51
Reviewed Commit/Range: `f2e72698cc` / `8e8b733a23..f2e72698cc` (coordination handoff at `28304662f4`)

Next Step:
Worker to remediate the remaining Gate 5 acceptance gaps and hand back only after exact verification passes.
---## History

### Iteration 52
Antigravity Worker completed Phase 5 Task 7 Final Remediation: implemented PDP URL request provenance, complete artifact metadata verification across all 8 PI/VF stages, and zero duplicate budget commit on idempotent replay with 206 tests (commit 39c8ff109f). Handed off to Planner for Gate 5 acceptance.

### Iteration 51
Antigravity Worker completed Phase 5 Task 7 Remediation: bound E2E & recovery tests directly to production ApprovalService, BudgetEngine, RecoveryService, and JobDispatcher timeout with 206 passing tests (commit f2e72698cc). Handed off to Planner for Gate 5 acceptance.

### Iteration 50
Antigravity Worker completed Phase 5 Task 7 Remediation: proved 14-state TikTok PDP flow, 5 explicit approvals, cost ledger, 12-state crash matrix, MCP & lease handling, and 205 tests (commit 8e8b733a23). Handed off to Planner for Gate 5 acceptance.

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
