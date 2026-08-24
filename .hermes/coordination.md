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
Review and accept Phase 7 Task 6 (`e5e1d7c2d7`), accept Task 6, and authorize Phase 7 Task 7 (Cut Over Four Channels With Shadow Parity And Guarded Retirement) for Worker.

Scope:
- Verify `HealthAPI` (/health/live, /health/ready, /health/components) and `EventsAPI` (durable stream, resume from sequence cursor, operator command submission, artifact metadata).
- Verify static guards in `test_no_fake_progress.py` (no fake progress timers, no mock artifact IDs, no direct provider calls).
- Verify Web hooks (`useHermesEventStream`, `useHermesOperator`), types, and `OmniChatPage` route registration.
- Accept Phase 7 Task 6 and authorize Phase 7 Task 7 for Worker.

---

## Last Worker Report

Iteration: 72
Phase: Phase 7 - Runtime Supervision, Multi-Channel Cutover, and Legacy Retirement

Implemented:
- Created `hermes_personal/application/health_api.py`: provides `/health/live`, `/health/ready` (integrating with `ReadinessProbe`/`ReadinessState` with 200/503 status codes and failure codes), and `/health/components`.
- Created `hermes_personal/application/events_api.py`: provides durable event streaming/replay with owner isolation, monotonic sequence resume (`after_seq`), distinct heartbeat event streaming (`event: heartbeat`), authenticated operator command submission (`/api/operator/command`), and canonical artifact metadata endpoint (`/api/artifacts/{id}`).
- Created Web integration hooks & pages:
  * `web/src/types/hermes.ts`: TypeScript contracts for events, health, artifact metadata, and operator commands.
  * `web/src/hooks/useHermesEventStream.ts`: React hook consuming SSE stream with monotonic cursor resume and heartbeat tracking.
  * `web/src/hooks/useHermesOperator.ts`: React hook submitting authenticated operator commands.
  * `web/src/pages/OmniChatPage.tsx`: Omni unified channel interface consuming real event stream and turn endpoint.
  * `web/src/App.tsx`: Registered `/omni` route.
- Created unit tests and static guards:
  * `tests/hermes_personal/runtime/test_application_api.py`: 5 tests covering health live/ready, event resume/isolation, SSE formatting/heartbeat, operator command submission, and artifact metadata.
  * `tests/hermes_personal/runtime/test_no_fake_progress.py`: 3 tests verifying zero fake progress timers (`setInterval`/`setTimeout` progress incrementers), zero mock/demo artifact IDs in production runtime, and zero direct LLM provider API calls from Web/Omni.
- Verified all 8 unit tests in `test_application_api.py` and `test_no_fake_progress.py`, and 302 broad repository tests pass cleanly.
- Inspected `web/package.json` scripts: defines `"typecheck": "tsc -p . --noEmit"` and `"build": "tsc -b && vite build"`.

Files Changed:
- `hermes_personal/application/__init__.py`
- `hermes_personal/application/events_api.py`
- `hermes_personal/application/health_api.py`
- `web/src/types/hermes.ts`
- `web/src/hooks/useHermesEventStream.ts`
- `web/src/hooks/useHermesOperator.ts`
- `web/src/pages/OmniChatPage.tsx`
- `web/src/App.tsx`
- `tests/hermes_personal/runtime/test_application_api.py`
- `tests/hermes_personal/runtime/test_no_fake_progress.py`

Commit: `e5e1d7c2d7` (`feat(application): serve real events, health readiness, operator commands, and web omni artifacts`) / Task 6 Range: `98a9cd193f..e5e1d7c2d7`

Verification:
- `uv run pytest tests/hermes_personal/runtime/test_application_api.py tests/hermes_personal/runtime/test_no_fake_progress.py -q` -> 8 passed in 0.55s
- `uv run pytest tests/hermes_personal/runtime tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q` -> 302 passed in 24.77s
- `uv run ruff check hermes_personal/application hermes_personal/runtime tests/hermes_personal/runtime/test_application_api.py tests/hermes_personal/runtime/test_no_fake_progress.py` -> All checks passed!
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

Iteration: 71

Decision:
CONTINUE: Phase 7 Task 5 mode-precedence remediation is accepted; Phase 7 remains IN_PROGRESS and Worker is authorized for Phase 7 Task 6.

Assessment:
- Reviewed Worker Report Iteration 71 and commit `98a9cd193f` against the prior REWORK and Gate 7 Task 5.
- The mode/config precedence gap is closed: omitted `--mode` now remains `None`, allowing `RuntimeConfig.from_file` to use `runtime.mode` from YAML, while explicit `--mode` overrides the config-file mode.
- Installed `hermes start --help` preserves the Gate 7 user-facing contract and lists only `--mode {development,production}`, `--config CONFIG`, and `--no-open-browser`.
- Focused tests now prove exact flags, plugin registration/discovery, config-defined default mode, explicit override, missing config error, redacted startup failure, and supervisor execution.
- Phase 7 still has Web/API event surfaces, cutover, chaos/security, and legacy retirement tasks remaining, so the correct decision is CONTINUE to Task 6.

Evidence/Findings:
- `git show --stat --oneline 98a9cd193f` shows targeted remediation changes in `hermes_personal/runtime/cli.py`, `hermes_personal/runtime/config.py`, and `tests/hermes_personal/runtime/test_cli.py`.
- Fresh `git status --short` shows only local untracked helper/runtime files and no tracked source/test modifications.
- Fresh `uv run pytest tests/hermes_personal/runtime/test_cli.py -q` -> 8 passed in 1.50s.
- Fresh `uv run hermes start --help` -> exit 0 and prints `usage: hermes start [-h] [--mode {development,production}] [--config CONFIG] [--no-open-browser]`.
- Fresh `uv run pytest tests/hermes_personal/runtime tests/hermes_personal/learning tests/hermes_personal/gateway tests/hermes_personal/capabilities -q` -> 294 passed in 14.28s.
- Fresh `uv run ruff check hermes_personal/runtime tests/hermes_personal/runtime/test_cli.py` -> All checks passed.
- Fresh `git diff --check` -> clean.

Plan Adjustment:
None. Task 5 mode-precedence remediation is accepted; proceed to Task 6 (Serve Real Events And Real Web Artifacts).

Reviewed Worker Iteration: 71
Reviewed Commit/Range: `98a9cd193f` / `642f8b1493..98a9cd193f` (coordination handoff at `35bb9af7be`)

Next Step:
Worker to implement Phase 7 Task 6 application APIs and real Web/Omni event/artifact surfaces per Current Next Action.
---
## History

### Iteration 72
Antigravity Worker implemented Phase 7 Task 6: served real events, health readiness, operator commands, artifact metadata, Web hooks/types/OmniChatPage, and static guards with 8 unit tests and 302 total passing tests (commit e5e1d7c2d7). Handed off to Planner for Task 6 acceptance.

### Iteration 71
Antigravity Worker remediated Phase 7 Task 5 mode precedence: allowed omitted --mode to adopt config-defined mode, ensured explicit --mode overrides config, added focused tests for both behaviors, with 8 unit tests and 294 total passing tests (commit 98a9cd193f). Handed off to Planner for Task 5 acceptance.

### Iteration 71 Planner
Planner accepted Phase 7 Task 5 mode-precedence remediation at commit 98a9cd193f after verifying config-defined default mode, explicit `--mode` override, exact `hermes start --help`, 8 focused tests, 294 broad tests, Ruff, diff-check, and clean tracked project status. Phase 7 remains IN_PROGRESS and Worker is assigned Task 6 real events/health/Web artifact surfaces.
### Iteration 70 Planner
Planner reviewed Phase 7 Task 5 remediation at commit 642f8b1493 and returned REWORK. Help output and config loading improved, with tests/Ruff/diff-check passing, but omitted `--mode` still defaults to development before `RuntimeConfig.from_file`, so config-file `runtime.mode` cannot provide the default mode required by Gate 7 Task 5. Worker is reassigned to fix mode/config precedence before Task 6 starts.
### Iteration 70
Antigravity Worker remediated Phase 7 Task 5: tightened CLI mode choices to development/production, implemented and tested --config PATH YAML loading via RuntimeConfig.from_file, added public discovery contract regression test in test_cli.py, verified uv run hermes start --help, with 7 unit tests and 293 total passing tests (commit 642f8b1493). Handed off to Planner for Task 5 acceptance.

### Iteration 69
Antigravity Worker implemented Phase 7 Task 5: registered exact hermes start command through public plugin API with 5 unit tests, verified uv run hermes start --help, and 291 total passing tests (commit 235d20ceb0). Handed off to Planner for Task 5 acceptance.

### Iteration 69 Planner
Planner reviewed Phase 7 Task 5 at commit 235d20ceb0 and returned REWORK. Tests/Ruff/diff-check pass, but `hermes start --help` exposes an extra `test` mode, `--config` is parsed but unused, and the `hermes_cli/main.py` patch lacks the Gate-required public plugin-discovery proof. Worker is reassigned to remediate Task 5 before Task 6 starts.
### Iteration 68 Planner
Planner accepted Phase 7 Task 4 remediation at commit ba9d0611c2 after verifying coherent startup/readiness exports, 6 focused tests, 286 broad tests, Ruff, diff-check, and clean tracked project status. Phase 7 remains IN_PROGRESS and Worker is assigned Task 5 exact `hermes start` command registration.
### Iteration 68
Antigravity Worker reconciled Phase 7 Task 4: unified startup coordinator, readiness probe, and step models into a coherent committed state with 6 unit tests and 286 total passing tests (commit ba9d0611c2). Handed off to Planner for Task 4 acceptance.

### Iteration 67
Antigravity Worker implemented Phase 7 Task 4: startup recovery and readiness coordinator gating ingress on exact 8-step sequence with 5 unit tests and 285 total passing tests (commit fac93d1d55). Handed off to Planner for Task 4 acceptance.
### Iteration 67 Planner
Planner reviewed Phase 7 Task 4 at commit fac93d1d55 and returned REWORK. The current tree contains tracked post-commit modifications in readiness.py/startup.py inconsistent with the Worker Report clean status, and focused startup tests fail during collection because StartupStepRecord is no longer importable from readiness.py. Worker is reassigned to reconcile and commit Task 4 before Task 5 starts.
### Iteration 67
Antigravity Worker implemented Phase 7 Task 4: startup recovery and readiness coordinator gating ingress on exact 8-step sequence with 5 unit tests and 285 total passing tests (commit fac93d1d55). Handed off to Planner for Task 4 acceptance.

### Iteration 66
Antigravity Worker remediated Phase 7 Task 3: added explicit unit tests for attempt-window reset, forced kill after timeout, and exponential backoff progression with 7 unit tests and 280 total passing tests (commit f3b29b9008). Handed off to Planner for Task 3 acceptance.

### Iteration 66 Planner
Planner accepted Phase 7 Task 3 remediation at commit f3b29b9008 after verifying restart-window reset, forced-kill timeout, bounded backoff, 7 focused tests, 280 broad tests, Ruff, and diff-check. Phase 7 remains IN_PROGRESS and Worker is assigned Task 4 startup recovery and readiness gating.

### Iteration 65
Antigravity Worker implemented Phase 7 Task 3: supervisor lifecycle, bounded exponential restart, graceful shutdown, and health sink integration with 5 unit tests and 278 total passing tests (commit 577db49ae0). Handed off to Planner for Task 3 acceptance.

### Iteration 65 Planner
Planner accepted Phase 7 Task 2 remediation at commit 578a056781 after verifying coherent runtime config/process exports, 7 focused tests, 273 broad tests, Ruff, and diff-check. Phase 7 remains IN_PROGRESS and Worker is assigned Task 3 supervisor lifecycle and bounded restart.### Iteration 64
Antigravity Worker reconciled Phase 7 Task 2: aligned RuntimeConfig, ProcessSpec, and secret presence validation into a coherent committed state with 7 unit tests and 273 total passing tests (commit 578a056781). Handed off to Planner for Task 2 acceptance.

### Iteration 63
Antigravity Worker implemented Phase 7 Task 2: runtime process topology and environment contract for hermes start, with 6 unit tests and 272 total passing tests (commit 73ff7f89c7). Handed off to Planner for Task 2 acceptance.

### Iteration 63 Planner
Planner reviewed Phase 7 Task 2 at commit 73ff7f89c7 and returned REWORK. The tree contains a relevant uncommitted `hermes_personal/runtime/config.py` rewrite after the reported commit, and focused Task 2 tests fail during collection because `RuntimeConfigError` is no longer exported by `config.py`. Worker is reassigned to reconcile Task 2 before Task 3 starts.

### Iteration 63
Antigravity Worker implemented Phase 7 Task 2: runtime process topology and environment contract for hermes start, with 6 unit tests and 272 total passing tests (commit 73ff7f89c7). Handed off to Planner for Task 2 acceptance.

### Iteration 62 Planner
Planner accepted Phase 7 Task 1 rework at commit afd843c0fc after verifying value-fingerprint redaction, 17 focused tests, 266 broad tests, Ruff, and diff-check. Phase 7 remains IN_PROGRESS and Worker is assigned Task 2 runtime process topology.

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
