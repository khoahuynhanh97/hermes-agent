# Hermes Coordination

## Overall Goal
Implement the Hermes Upstream Gateway Rearchitecture program: converge Telegram, CLI, Web, and Omni natural-language ingress onto one canonical Hermes Agent Turn path; add stable capabilities, durable workflows, shared approvals/budgets, governed learning, and one-command runtime supervision while preserving legacy data and avoiding live paid-provider calls in verification.

## Overall Status
IN_PROGRESS

## Current Phase
Phase 6 - Governed Learning Memory And Knowledge

## Current Owner
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
Review and accept Phase 6 / Gate 6 approved-only retrieval remediation and authorize Phase 7 (Runtime Supervision, Multi-Channel Cutover, and Legacy Retirement).

Scope of Review:
- `hermes_personal/learning/retrieval.py`: `ApprovedLearningRetriever` strictly restricts retrieval to candidates where `cand.status == "approved"`, `v.status == "active"`, and `cand.owner_user_id == owner_user_id`. `draft`, `evaluated`, `pending_approval`, and `rejected` statuses are strictly excluded.
- `tests/hermes_personal/learning/test_retrieval.py`: Includes explicit test cases for `draft`, `evaluated`, and `pending_approval` active version exclusion and approved active version retrieval.
- `tests/hermes_personal/learning/test_context_integration.py`: Proves unapproved candidate content cannot enter `AgentContextAssembler` or later Agent Turn context.
- Verification across the 249-test suite, Ruff static analysis, and diff checks.

Exact Verification:
- `uv run pytest tests/hermes_personal/learning/test_retrieval.py tests/hermes_personal/learning/test_context_integration.py tests/hermes_personal/learning/test_learning_e2e.py -q` -> 11 passed in 1.66s
- `uv run pytest tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q` -> 249 passed in 13.79s
- `uv run ruff check hermes_personal/learning tests/hermes_personal/learning hermes_personal/storage/sqlite.py` -> All checks passed!
- `git diff --check` -> Clean (0 whitespace/diff errors)
- `git status --short` -> Clean (only local untracked helper scripts remain)

---

## Last Worker Report

Iteration: 59
Phase: Phase 6 - Governed Learning Memory And Knowledge

Implemented:
- Remedied `ApprovedLearningRetriever` in `hermes_personal/learning/retrieval.py`: retrieval now strictly requires `cand.status == "approved"`, `v.status == "active"`, and `cand.owner_user_id == owner_user_id`. Candidates with `draft`, `evaluated`, `pending_approval`, or `rejected` status are completely excluded from returning results even if an active `learning_version` row exists.
- Added regression tests in `tests/hermes_personal/learning/test_retrieval.py`:
  - `test_active_version_attached_to_draft_candidate_not_retrieved`
  - `test_active_version_attached_to_evaluated_candidate_not_retrieved`
  - `test_active_version_attached_to_pending_approval_candidate_not_retrieved`
  - `test_approved_active_version_retrieves_normally`
- Added integration test `test_unapproved_candidate_cannot_enter_turn_context` in `tests/hermes_personal/learning/test_context_integration.py` proving unapproved knowledge never leaks into `AgentContextAssembler` or `HermesTurnService` prompt history.
- Normalized coordination file heading to `## Current Owner` and updated status.

Files Changed:
- `hermes_personal/learning/retrieval.py`
- `tests/hermes_personal/learning/test_context_integration.py`
- `tests/hermes_personal/learning/test_retrieval.py`

Commit: `d57157b8f9` (`fix(learning): enforce approved-only retrieval for active learning`)

Verification:
- `uv run pytest tests/hermes_personal/learning/test_retrieval.py tests/hermes_personal/learning/test_context_integration.py tests/hermes_personal/learning/test_learning_e2e.py -q` -> 11 passed in 1.66s
- `uv run pytest tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q` -> 249 passed in 13.79s
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

Iteration: 59

Decision:
REWORK Phase 6 / Gate 6 before accepting the phase or authorizing Phase 7.

Assessment:
- Reviewed Worker Report Iteration 58 and Gate 6 commit range `622f7720e3..0d03694715` against `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-6.md`.
- Independent verification passed: `uv run pytest tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q` -> 244 passed; `uv run ruff check hermes_personal/learning tests/hermes_personal/learning hermes_personal/storage/sqlite.py` -> passed; `git diff --check` -> clean.
- Production schema duplicate check is resolved: only one `CREATE TABLE IF NOT EXISTS candidate_evaluation` remains in `hermes_personal/storage/sqlite.py`.
- However, Gate 6 exit criterion "approved-only retrieval" is not satisfied. `ApprovedLearningRetriever` currently permits candidate statuses `draft` and `evaluated` to influence retrieval when an active version exists.

Findings / Evidence:
- `hermes_personal/learning/retrieval.py` checks `cand.status not in ("approved", "evaluated", "draft")`, which explicitly allows `draft` and `evaluated` candidates.
- A local probe using the production SQLite path created a `draft` knowledge candidate, created an active version, and `ApprovedLearningRetriever.retrieve(owner_user_id="u1", query="draft knowledge")` returned it: `retrieved_count=1`, candidate `draft_c`.
- The coordination file also had `### Current Owner`; this review normalizes it back to the canonical `## Current Owner` heading to keep scheduler/guard parsing stable.
- This violates Gate 6 constraints: failed/unapproved artifacts cannot become positive learning, and only approved relevant knowledge may reach later Agent Turns.

Plan Adjustment:
- Reason: Worker completed broad Gate 6 implementation and tests, but retrieval tests missed active-version rows attached to unapproved candidate statuses.
- Impact: Accepting Gate 6 now could allow unapproved draft/evaluated knowledge to affect future Agent Turns.
- Affected phases/tasks: Phase 6 Task 4 approved retrieval and Task 7 end-to-end acceptance; Phase 7 remains unauthorized.
- Proposed correction: Restrict retrieval to `cand.status == "approved"` and add regression/E2E coverage for draft/evaluated/pending approval exclusion.

Reviewed Worker Iteration: 58
Reviewed Commit/Range: `0d03694715` / `622f7720e3..0d03694715`

Next Step:
Worker to remediate approved-only retrieval and report Iteration 59 back to PLANNER.

---

## History

### Iteration 59
Worker remediated approved-only retrieval in `hermes_personal/learning/retrieval.py` (commit `d57157b8f9`), requiring `cand.status == "approved"` and excluding `draft`, `evaluated`, `pending_approval`, and `rejected` candidates. Added unit regression tests in `test_retrieval.py` and turn context integration test in `test_context_integration.py`. Verified 249 tests passing across learning, gateway, and capabilities suites. Handed off to Planner for Gate 6 acceptance.
### Iteration 59
Planner reviewed Worker Iteration 58 (`0d03694715`) and chose REWORK. Gate 6 broad verification passed, but approved-only retrieval is violated because active versions for `draft`/`evaluated` candidates can be returned. Ownership returned to WORKER for approved-only retrieval remediation.
### Iteration 58
Worker resolved Phase 6 Task 1 schema hygiene rework and implemented Phase 6 Tasks 2-7 end-to-end: CandidateEvaluator policy, Approval-gated promotion/rollback, Approved retrieval & AgentContext turn injection, PreferenceMemoryPolicy & USER.md projection, ProceduralSkillPublisher & rollback, LearningMetricsEngine, and complete E2E acceptance test suite with 244 passing tests (commit range `622f7720e3..a40eeff721`). Handed off to Planner for Gate 6 acceptance.
### Iteration 57
Planner reviewed Phase 6 Task 1 rework at commit 622f7720e3. Tests, Ruff, and diff-check pass, and evaluation persistence/immutable outcome behavior is present. Planner returned REWORK because production `sqlite.py` still contains duplicate/conflicting `candidate_evaluation` DDL and tests build their own fixture schema instead of proving the production schema path. Phase 6 remains IN_PROGRESS on Task 1.
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
