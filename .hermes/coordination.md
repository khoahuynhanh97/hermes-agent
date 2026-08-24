# Hermes Coordination

## Overall Goal
Implement the Hermes Upstream Gateway Rearchitecture program: converge Telegram, CLI, Web, and Omni natural-language ingress onto one canonical Hermes Agent Turn path; add stable capabilities, durable workflows, shared approvals/budgets, governed learning, and one-command runtime supervision while preserving legacy data and avoiding live paid-provider calls in verification.

## Overall Status
IN_PROGRESS

## Current Phase
Phase 7 - Runtime Supervision, Multi-Channel Cutover, and Legacy Retirement

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
Status: COMPLETED
Goal: Add governed learning, approved retrieval, skill publication, rollback, and metrics. (Accepted by Planner at commit d57157b8f9).

### Phase 7
Status: IN_PROGRESS
Goal: Deliver hermes start, health/readiness, restart behavior, four-channel cutover, and legacy retirement guards.

---

## Current Next Action

Owner: PLANNER

Objective:
Review and accept Phase 7 Task 1 Rework (`afd843c0fc`), accept Task 1, and authorize Phase 7 Task 2 (Define Runtime Process Topology And Environment Contract) for Worker.

Scope:
- Verify `redact()` in `hermes_personal/observability/redaction.py` supporting `value_fingerprints: Sequence[str | Pattern[str]]`.
- Verify value fingerprint regression tests in `tests/hermes_personal/runtime/test_observability.py`.
- Accept Phase 7 Task 1 and authorize Phase 7 Task 2 for Worker.

---

## Last Worker Report

Iteration: 62
Phase: Phase 7 - Runtime Supervision, Multi-Channel Cutover, and Legacy Retirement

Implemented:
- Updated `hermes_personal/observability/redaction.py`:
  * API Shape: `redact(data: Any, sensitive_keys: Sequence[str] = DEFAULT_SECRET_KEY_PATTERNS, value_fingerprints: Sequence[str | Pattern[str]] = ()) -> Any`
  * API Shape: `redact_string(value: str, value_fingerprints: Sequence[str | Pattern[str]] = ()) -> str`
  * Supports string substring matches as well as compiled regex `re.Pattern` value fingerprints.
  * Recursively redacts across dict values, list items, tuple elements, and set members.
- Exported `redact_string` in `hermes_personal/observability/__init__.py`.
- Added focused regression tests in `tests/hermes_personal/runtime/test_observability.py`:
  * `test_configured_value_fingerprint_redaction_under_safe_keys`: validates secret tokens under innocent keys like `description`, `nested_item.stdout`, `log_lines`, `tuple_items`, `set_items` are masked.
  * `test_configured_value_fingerprint_regex_patterns`: validates regex pattern matching for API key formats (`sk-...`).
  * `test_redact_string_directly`: validates standalone string redaction helper.
- Verified all 17 observability unit tests and 266 total repository tests pass cleanly.

Files Changed:
- `hermes_personal/observability/__init__.py`
- `hermes_personal/observability/redaction.py`
- `tests/hermes_personal/runtime/test_observability.py`

Commit: `afd843c0fc` (`feat(observability): support configured value fingerprints and regex patterns in redaction`) / Task 1 Range: `3f4e2f9eb2..afd843c0fc`

Verification:
- `uv run pytest tests/hermes_personal/runtime/test_observability.py -q` -> 17 passed in 0.60s
- `uv run pytest tests/hermes_personal/runtime tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q` -> 266 passed in 15.03s
- `uv run ruff check hermes_personal/observability tests/hermes_personal/runtime/test_observability.py` -> All checks passed!
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

Iteration: 61

Decision:
REWORK: Phase 7 Task 1 is not accepted. Focused tests and Ruff pass, but the implementation does not satisfy the Gate 7 redaction contract for configured value fingerprints.

Assessment:
- Reviewed Worker Report Iteration 61 and commit `3f4e2f9eb2` against Gate 7 Task 1.
- `CorrelationContext` preserves owner/session/turn/workflow/job/approval/tool IDs and supports child context inheritance.
- `ComponentHealth` and `HealthReport` define the required status vocabulary and readiness/liveness aggregation for required vs optional components.
- `redact()` recursively handles dict/list/tuple/set structures and masks values when the key name is sensitive.
- Acceptance gap: Gate 7 Task 1 explicitly requires redaction "by normalized key and configured value fingerprints before serialization." Current `redact()` has no configured value-fingerprint parameter/path and returns primitive string values unchanged under safe-looking keys, so a known secret value can leak if the key is not classified as sensitive. The focused tests also do not cover this requirement.

Evidence/Findings:
- `hermes_personal/observability/redaction.py` exposes `redact(data, sensitive_keys=...)` only; it has no configured sensitive-value/fingerprint input and no primitive value matching branch.
- `tests/hermes_personal/runtime/test_observability.py` verifies key-based masking and primitive pass-through, but not value-fingerprint masking.
- Fresh verification: `uv run pytest tests/hermes_personal/runtime/test_observability.py -q` -> 14 passed in 0.89s.
- Fresh verification: `uv run ruff check hermes_personal/observability tests/hermes_personal/runtime/test_observability.py` -> All checks passed.
- Fresh verification: `git diff --check` -> clean.
- `git status --short` shows only local untracked helper/runtime files (`build/`, `coord.txt`, `create_shortcut.vbs`, `launch_gui.vbs`, `run_worker.bat`, `update_coord.py`, `worker-prompt.txt`, `worker-scheduler.ps1`, `worker.ps1`).

Plan Adjustment:
Reason: Worker Report claimed redaction completion, but the implementation/tests cover key-based recursion only and miss Gate 7's configured value-fingerprint requirement.
Impact: Phase 7 Task 1 remains incomplete; Task 2 must not start because later runtime logs/health/process specs depend on safe redaction.
Affected phases/tasks: Phase 7 Task 1 redaction contract; Phase 7 Task 2 process topology.
Proposed correction: Add configured value-fingerprint matching to `redact()`, add focused tests proving raw secret values are masked under safe-looking keys and nested structures, rerun verification, and hand off with a new commit/range.

Reviewed Worker Iteration: 61
Reviewed Commit/Range: `3f4e2f9eb2` / `d57157b8f9..3f4e2f9eb2` (coordination handoff at `6e00d6f27b`)

Next Step:
Worker to implement configured value-fingerprint redaction and tests, then re-handoff Phase 7 Task 1.
---

## History

### Iteration 62
Antigravity Worker reworked Phase 7 Task 1: added configured value fingerprints (literal substrings and regex patterns) to `redact()` with 17 unit tests and 266 total passing tests (commit afd843c0fc). Handed off to Planner for Task 1 acceptance.

### Iteration 61
Planner accepted Phase 6 / Gate 6 at commit d57157b8f9 after verifying approved-only retrieval remediation, 11 focused tests, 249 broad tests, Ruff, and diff-check. Phase 6 is COMPLETED, Phase 7 is IN_PROGRESS, and Worker is assigned Phase 7 Task 1 for runtime observability contracts.
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
