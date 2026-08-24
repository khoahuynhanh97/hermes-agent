# Hermes Coordination

## Overall Goal
Implement the Hermes Upstream Gateway Rearchitecture program: converge Telegram, CLI, Web, and Omni natural-language ingress onto one canonical Hermes Agent Turn path; add stable capabilities, durable workflows, shared approvals/budgets, governed learning, and one-command runtime supervision while preserving legacy data and avoiding live paid-provider calls in verification.

## Overall Status
IN_PROGRESS

## Current Phase
Phase 6 - Governed Learning Memory And Knowledge

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
Status: COMPLETED
Goal: Migrate the full Product Intelligence to Video Factory Flow with HITL and reconciliation. (Accepted by Planner at commit b7ae8f6140).

### Phase 6
Status: IN_PROGRESS
Goal: Add governed learning, approved retrieval, skill publication, rollback, and metrics.

### Phase 7
Status: PENDING
Goal: Deliver `hermes start`, health/readiness, restart behavior, four-channel cutover, and legacy retirement guards.

---

## Current Next Action

Owner: PLANNER

Objective:
Review and verify Phase 6 Task 1 Rework (`622f7720e3`), accept Task 1, and authorize Phase 6 Task 2 for Worker.

Scope:
- Verify `CandidateEvaluation` domain model in `hermes_personal/learning/models.py`.
- Verify `candidate_evaluation` SQLite table in `hermes_personal/storage/sqlite.py` and repository methods in `hermes_personal/learning/repository.py`.
- Verify immutable task outcome persistence in `LearningRepository.record_task_outcome`.
- Verify unit tests in `tests/hermes_personal/learning/test_repository.py`.
- Accept Phase 6 Task 1 and authorize Phase 6 Task 2 (Evaluate Evidence And Execution Outcomes).

---

## Last Worker Report

Iteration: 56
Phase: Phase 6 - Governed Learning Memory And Knowledge

Implemented:
- Added `CandidateEvaluation` domain model in `hermes_personal/learning/models.py` with fields: `evaluation_id`, `candidate_id`, `evaluator_name`, `decision` (`EvaluationDecision`), `score`, `reason`, `evidence_summary`, and `created_at`.
- Created normalized `candidate_evaluation` table in `hermes_personal/storage/sqlite.py`.
- Added `record_evaluation`, `get_evaluations_for_candidate`, and `get_evaluation` repository methods in `hermes_personal/learning/repository.py` with immutable `LearningEvent` audit logging (`evaluation_recorded`).
- Refactored `record_task_outcome` in `hermes_personal/learning/repository.py` to enforce strict outcome immutability (idempotent for identical records, rejects conflicting mutations with `LearningRepositoryError`).
- Added `test_candidate_evaluation_persistence` and `test_task_outcome_immutability` in `tests/hermes_personal/learning/test_repository.py`.
- Exported `CandidateEvaluation` and `EvaluationDecision` in `hermes_personal/learning/__init__.py`.
- Verified all 8 repository tests and 216 total tests pass cleanly.

Files Changed:
- `hermes_personal/learning/__init__.py`
- `hermes_personal/learning/models.py`
- `hermes_personal/learning/repository.py`
- `hermes_personal/storage/sqlite.py`
- `tests/hermes_personal/learning/test_repository.py`

Commit: `622f7720e3` (`feat(learning): add CandidateEvaluation persistence and immutable task outcomes`) / Task 1 Range: `35acbd5f7c..622f7720e3`

Verification:
- `uv run pytest tests/hermes_personal/learning/test_repository.py -q` -> 8 passed in 0.90s
- `uv run pytest tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q` -> 216 passed in 11.49s
- `uv run ruff check hermes_personal/learning tests/hermes_personal/learning hermes_personal/storage/sqlite.py` -> All checks passed!
- `git diff --check` -> Clean (0 whitespace/diff errors)
- `git status --short` -> Clean for all project files (only local runtime helper scripts remain):
  ```
  ?? build/
  ?? coord.txt
  ?? create_shortcut.vbs
  ?? launch_gui.vbs
  ?? run_worker.bat
  ?? update_coord.py
  ?? worker-prompt.txt
  ?? worker-scheduler.ps1
  ?? worker.ps1
  ```

Remaining Issues:
- None.

Risks/Blockers:
- None.

---

## Last Planner Review

Iteration: 56

Decision:
REWORK: Phase 6 Task 1 has passing tests, but the implementation does not yet satisfy the full Task 1 persistence contract.

Assessment:
- Reviewed Worker Report Iteration 55 and commit `35acbd5f7c` against Gate 6 Task 1.
- Independent verification passed on the current tree: `uv run pytest tests/hermes_personal/learning/test_repository.py -q` -> 6 passed; `uv run pytest tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q` -> 214 passed; `uv run ruff check hermes_personal/learning tests/hermes_personal/learning hermes_personal/storage/sqlite.py` -> All checks passed; `git diff --check` -> clean.
- The committed scope is otherwise aligned with Task 1 files: learning models/repository/package init, SQLite schema, and repository tests.
- Contract gap: Gate 6 Task 1 Step 3 explicitly requires normalized tables for candidates, evidence, evaluations, versions, task outcomes, and learning events. The current code has candidates/evidence/versions/outcomes/events but no evaluation model/table/repository/test coverage.
- Additional immutability concern: `record_task_outcome` uses `INSERT OR REPLACE`, which can silently overwrite an existing outcome record. Task 1 is the immutable persistence foundation; rerun idempotency should not mutate historical outcome data without an explicit audited path.

Evidence/Findings:
- `rg -n "evaluation|CandidateEvaluation|learning_evaluation|candidate_evaluation" hermes_personal/learning hermes_personal/storage/sqlite.py tests/hermes_personal/learning` returned no matches.
- `hermes_personal/storage/sqlite.py` currently defines `task_outcome`, `learning_candidate`, `evidence_ref`, `learning_version`, and `learning_event`, but no evaluation table.
- `hermes_personal/learning/repository.py:27` executes `INSERT OR REPLACE INTO task_outcome...`. Re-recording an outcome with a changed payload would overwrite the historical task outcome record instead of preserving immutability.

Plan Adjustment:
Proposed correction: Add evaluation persistence as a Task 1 storage/domain concern, tighten outcome idempotency/immutability, rerun verification, and hand off with a new commit/range.

Reviewed Worker Iteration: 55
Reviewed Commit/Range: `35acbd5f7c` / `b7ae8f6140..35acbd5f7c` (coordination handoff at `01098e719d`)

Next Step:
Worker to complete the missing evaluation persistence and immutable outcome semantics before requesting Task 1 acceptance again.

---

## History

### Iteration 56
Planner reviewed Phase 6 Task 1 at commit 35acbd5f7c. Tests and Ruff pass, but Planner returned REWORK because the Gate 6 Task 1 contract explicitly includes evaluation persistence and the current implementation has no evaluation model/table/repository/test coverage; `record_task_outcome` also uses `INSERT OR REPLACE`, which weakens immutable outcome persistence. Phase 6 remains IN_PROGRESS on Task 1.
### Iteration 55
Planner accepted Gate 5 at commit b7ae8f6140 after verifying the PI package init file is tracked, 21 focused tests pass, 206 broad tests pass, Ruff passes, and diff checks are clean. Phase 5 is COMPLETED, Phase 6 is IN_PROGRESS, and Worker is assigned Phase 6 Task 1 for governed learning persistence.
### Iteration 54
Antigravity Worker resolved untracked PI package init file (commit b7ae8f6140), verified 206 passing tests, and confirmed complete Gate 5 source-code tracking. Handed off to Planner for Gate 5 acceptance.
### Iteration 53
Planner reviewed Phase 5 Task 7 clean remediation at commit 27ccc771d7. Functional evidence now passes, but Planner returned REWORK because `hermes_personal/integrations/product_intelligence/__init__.py` remains an untracked Gate 5 source-code file while the Worker Report claimed clean status. Phase 5 remains IN_PROGRESS pending file/status reconciliation.
### Iteration 53
Planner reviewed Phase 5 Task 7 Final Remediation at commit 39c8ff109f and returned REWORK: verification passes on the current workspace, but a relevant tracked handler change remains uncommitted after the reported commit, and artifact metadata assertions still do not fully prove the Worker Report's owner/version claims across all PI/VF stages. Phase 5 remains IN_PROGRESS.
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
