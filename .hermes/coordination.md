# Hermes Coordination

## Overall Goal
Implement the Hermes Upstream Gateway Rearchitecture program: converge Telegram, CLI, Web, and Omni natural-language ingress onto one canonical Hermes Agent Turn path; add stable capabilities, durable workflows, shared approvals/budgets, governed learning, and one-command runtime supervision while preserving legacy data and avoiding live paid-provider calls in verification.

## Overall Status
IN_PROGRESS

## Current Phase
Phase 3 - Capability Catalog & Domain Skills

## Current Owner
ANTIGRAVITY

## Overall Plan

### Phase 0
Status: COMPLETED
Goal: Restore the missing `.hermes/coordination.md` source of truth and reconcile the current implementation state with the approved gateway rearchitecture program.

### Phase 1
Status: COMPLETED
Goal: Establish clean upstream baseline, provenance, canonical contracts, and compatibility suite. (Accepted by Codex at commit 10bb230b22).

### Phase 2
Status: COMPLETED
Goal: Converge all natural-language ingress onto one Agent Turn path with global identity, per-channel sessions, and explicit handoff. (Accepted by Codex at commit 1efe9c6909).

### Phase 3
Status: IN_PROGRESS
Goal: Add stable capability catalog, MCP snapshots, active snapshot pointer, policy, Tool Search adapter, governed domain skills, structured errors, and end-to-end turn execution.

### Phase 4
Status: PENDING
Goal: Implement durable workflows, shared approvals, budgets, jobs, and restart recovery.

### Phase 5
Status: PENDING
Goal: Migrate the full Product Intelligence to Video Factory flow with HITL and reconciliation.

### Phase 6
Status: PENDING
Goal: Add governed learning, approved retrieval, skill publication, rollback, and metrics.

### Phase 7
Status: PENDING
Goal: Deliver `hermes start`, health/readiness, restart behavior, four-channel cutover, and legacy retirement guards.

---

## Current Next Action

Owner: ANTIGRAVITY

Objective:
Persist the corrected Gate 3 plan in the authoritative worktree, resolve the remaining architecture inconsistencies, then implement Gate 3 Task 1 only.

Scope:
- Work only in `D:\work\hermes-upstream-rearchitecture`; leave the legacy dirty workspace and untracked `build/` untouched.
- Replace the stale repository plan at `docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-3.md` with the corrected plan. The external Antigravity `implementation_plan.md` is not an SSOT.
- Preserve the existing public `AIAgent.run_conversation` / `PublicAIAgent` call contract. Runtime governance must integrate through the existing tool-definition assembly/execution path or a compatibility-preserving adapter; do not add required `run_conversation` parameters.
- Define `capability_catalog_state` as a singleton row (for example `state_id INTEGER PRIMARY KEY CHECK(state_id = 1)`) with an FK to the immutable snapshot, and activate it in the same transaction as validated snapshot persistence.
- Do not place provider-specific or MCP wire names statically in governed skills. Keep stable IDs in `allowed-capabilities`; use the existing `tool_search`, `tool_describe`, and `tool_call` bridges or a policy-generated active binding scope for upstream compatibility.
- Keep the E2E contract explicit: all four ingress normalizers (Telegram, CLI, Web, Omni) converge to the canonical turn path, while one hermetic representative turn proves governed search, fake MCP execution, `tool_activity`, and terminal event behavior.
- After the plan is corrected, implement only Task 1: the initial stable capability manifest/bindings and focused tests. Do not start snapshots, policy, search, skills, or runtime integration yet.

Expected Result:
- The version-controlled Gate 3 plan contains all eight prior fixes plus the four clarifications above.
- Task 1 declares exactly the ten approved stable capability IDs, excludes `note.create`, uses existing Gate 1 contract types where appropriate, and has explicit input/output schema versions, ownership, risk, cost, approval, skill, and workflow metadata.
- Update `Last Worker Report` with exact files, commit(s), test evidence, remaining issues, and set `Current Owner = CODEX`.

Verification:
- `uv run pytest tests/hermes_personal/capabilities/test_manifest.py tests/hermes_personal/contracts/test_capability.py -q`
- Focused Ruff check for files changed in Task 1.
- `git diff --check 1efe9c6909..HEAD`
- No network or paid-provider calls.

---

## Last Worker Report

Iteration: 1

Implemented:
- Recovered workflow continuity and mapped workspace layout:
  - Worktree Authority: `D:\work\hermes-upstream-rearchitecture` on branch `codex/hermes-upstream-rearchitecture` is the clean, verified target environment for the upstream gateway rearchitecture program.
  - Legacy Workspace: `D:\work\hermes-agent` on branch `codex/hermes-orchestrator-unification` contains legacy uncommitted experimentation code prior to rearchitecture design lock.
- Gate 1 Status: Fully implemented, verified, and ACCEPTED by Codex at commit `10bb230b22`.
- Gate 2 Status: Fully implemented, remediated across 6 review cycles, verified with 131 `hermes_personal` tests + 120 upstream regression tests (251 passed total), and officially ACCEPTED by Codex at commit `1efe9c6909`.
- Gate 3 Status: Implementation plan updated with all 8 Codex required fixes (`implementation_plan.md`). Ready for Task 1 execution.

Files Changed (Gate 1 & Gate 2 in `D:\work\hermes-upstream-rearchitecture`):
- `hermes_personal/contracts/` (`principal.py`, `request.py`, `operator.py`, `events.py`, `serialization.py`, `capability.py`)
- `hermes_personal/identity/` (`repository.py`)
- `hermes_personal/sessions/` (`repository.py`, `upstream_transcript.py`)
- `hermes_personal/gateway/` (`normalizers.py`)
- `hermes_personal/orchestration/` (`turn_service.py`, `upstream_agent.py`, `event_repository.py`)
- `hermes_personal/storage/` (`sqlite.py` schema v1 + `user_message` + `legacy_session_cutover`)
- `tests/hermes_personal/` (14 test files, 131 tests)

Commands Executed:
- `uv run pytest tests/hermes_personal/gateway tests/hermes_personal/contracts tests/hermes_personal/test_upstream_compatibility.py -q` -> 131 passed in 7.51s
- `uv run pytest tests/tools/test_registry.py tests/tools/test_mcp_capability_gating.py tests/gateway/test_session.py -q` -> 120 passed in 7.78s
- `uv run ruff check hermes_personal/orchestration/__init__.py hermes_personal/orchestration/event_repository.py hermes_personal/orchestration/turn_service.py hermes_personal/orchestration/upstream_agent.py hermes_personal/storage/sqlite.py tests/hermes_personal/gateway/test_event_repository.py tests/hermes_personal/gateway/test_gateway_acceptance.py tests/hermes_personal/gateway/test_no_semantic_router.py tests/hermes_personal/gateway/test_turn_service.py` -> All checks passed
- `git diff --check f9c09ddec6..1efe9c6909` -> Clean (0 whitespace defects)

Verification:
- PASS: All 251 tests passed cleanly across Gate 1, Gate 2, and upstream regression suites. Zero network or paid API calls.

Remaining Issues:
- None for Gate 1 or Gate 2.
- Uncommitted legacy diff in `D:\work\hermes-agent` (branch `codex/hermes-orchestrator-unification`) should remain untouched while work continues cleanly in `D:\work\hermes-upstream-rearchitecture`.

Risks/Blockers:
- None. Gate 3 implementation is ready to begin under the updated 8-point plan.

Recommended Current Phase:
Phase 3 - Capability Catalog & Domain Skills

---

## Last Planner Review

Iteration: 1

Decision:
REWORK

Assessment:
- Phase 0 recovery is accepted. The authoritative implementation worktree is `D:\work\hermes-upstream-rearchitecture` at `1efe9c6909`.
- Gate 1/2 baseline was independently rerun by CODEX: 131 Hermes Personal tests and 120 upstream regression tests passed; `git diff --check f9c09ddec6..HEAD` was clean.
- Gate 3 direction is correct, but Task 1 is not authorized from the current repository plan because the corrected plan exists only in Antigravity's external brain directory while the checked-in Gate 3 plan remains stale.

Issues:
- Repository SSOT still specifies `latest()` snapshots, strict rejection of all degraded capabilities, a parallel lexical search service, and the old skill layout.
- The proposed active-pointer DDL does not enforce a singleton row.
- Passing new required governance parameters into `AIAgent.run_conversation` would break the upstream compatibility boundary established by Gate 2.
- Static MCP wire names in `allowed-tools` would make skills stale after rebinding and contradict stable capability IDs.

Plan Adjustment:
- Reason: The updated external plan is not version-controlled and still leaves runtime compatibility, singleton activation, and skill rebinding ambiguous.
- Impact: Planning correction only; original goal and accepted Gate 1/2 behavior do not change.
- Affected phases: Phase 3 directly; Phases 4-7 inherit the stable capability and runtime contracts.
- Proposed change: Persist the corrected Gate 3 plan in the worktree, preserve the public AIAgent call signature, enforce singleton atomic activation, use bridge/dynamic tool scope instead of static wire names, and explicitly retain four-ingress convergence in acceptance.

Next Step:
ANTIGRAVITY must apply the plan corrections and then implement Gate 3 Task 1 only, verify it, report evidence, and transfer ownership back to CODEX.

---

## History

### Iteration 2
CODEX accepted Phase 0 recovery and independently confirmed the Gate 1/2 baseline with 251 passing tests. CODEX found that the corrected Gate 3 plan was stored only outside the repository and identified remaining compatibility and SSOT ambiguities. Decision: REWORK. Ownership was transferred to ANTIGRAVITY with permission to correct the checked-in plan and implement Task 1 only.

### Iteration 1
ANTIGRAVITY reconciled the workspace state: mapped `D:\work\hermes-upstream-rearchitecture` as the primary worktree (commit `1efe9c6909`, 251/251 tests green), updated `.hermes/coordination.md`, incorporated all 8 required fixes into the Gate 3 implementation plan (`implementation_plan.md`), and transferred ownership to CODEX for Phase 3 authorization.

### Iteration 0
CODEX found that `.hermes/coordination.md` was missing, created the file from program docs, marked Phase 0 as IN_PROGRESS, and handed recovery to ANTIGRAVITY.
