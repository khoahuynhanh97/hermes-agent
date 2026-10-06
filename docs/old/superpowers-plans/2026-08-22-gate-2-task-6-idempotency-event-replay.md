# Gate 2 Task 6 Idempotency And Event Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Gate 2 with durable duplicate-turn idempotency, exact SQLite event replay, and executable gateway/security boundaries.

**Architecture:** A required SQLite `EventRepository` atomically claims `(owner_user_id, idempotency_key)` after turn authorization, stores a canonical request digest and the first turn/session identity, and persists immutable serialized `AgentEvent` rows keyed by `(turn_id, sequence)`. `HermesTurnService` replays terminal rows before touching transcript or agent state, rejects digest conflicts and in-progress duplicates with typed exceptions, and persists every live event to both stores before yielding.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, frozen dataclasses, `pytest`, `pytest-asyncio`, `ruff`.

## Global Constraints

- Do not use external services, edit upstream code outside the project adapter packages, or cut over production routes.
- Validate identity, session, and workflow authorization before an execution claim.
- Never fall back to process memory; replay must survive closing and reopening SQLite.
- Commit source, tests, and docs only. Keep `.superpowers/sdd/gate-2-task-6-report.md` ignored.

---

### Task 1: Durable Execution And Event Repository

**Files:**
- Create: `hermes_personal/orchestration/event_repository.py`
- Modify: `hermes_personal/storage/sqlite.py`
- Create: `tests/hermes_personal/gateway/test_event_repository.py`

**Interfaces:**
- Produces: `EventRepository.claim(request) -> tuple[AgentEvent, ...] | None`, `append_event(event)`, `mark_terminal(turn_id, status)`, `IdempotencyConflict`, and `TurnInProgress`.

- [ ] Write focused failing tests for new schema, canonical claim behavior, conflicts, concurrent in-progress claims, event FK/uniqueness, terminal replay, immutable reconstruction, and replay after reconnect.
- [ ] Run `uv run pytest tests/hermes_personal/gateway/test_event_repository.py -q` and confirm failures are caused by the missing repository/schema.
- [ ] Add the minimal schema and repository implementation using `BEGIN IMMEDIATE`, canonical sorted JSON hashing, and ordered event deserialization.
- [ ] Re-run the focused repository tests until green.

### Task 2: Turn Service Binding

**Files:**
- Modify: `hermes_personal/orchestration/turn_service.py`
- Modify: `hermes_personal/orchestration/__init__.py`
- Modify: `hermes_personal/contracts/events.py`
- Modify: `tests/hermes_personal/gateway/test_turn_service.py`

**Interfaces:**
- Consumes: required `EventRepository` dependency.
- Produces: auth-before-claim execution, exact terminal replay, replay-store/transcript persistence before yield, and completed/failed status transitions.

- [ ] Update fixtures and add failing service tests for no transcript/agent duplication, conflict, in-progress, auth-before-claim, exact IDs/order, and failed replay.
- [ ] Run the focused service tests and confirm expected RED failures.
- [ ] Bind the repository after validation and before transcript access; store live events before transcript append/yield; mark terminal events only after both stores accept them.
- [ ] Re-run repository and service tests until green.

### Task 3: Acceptance And Static Boundaries

**Files:**
- Create: `tests/hermes_personal/gateway/test_gateway_acceptance.py`
- Create: `tests/hermes_personal/gateway/test_no_semantic_router.py`
- Create: `docs/hermes-personal/gateway.md`

**Interfaces:**
- Consumes: all Gate 2 normalizers, repositories, service, and `UpstreamAIAgentAdapter`.
- Produces: executable four-channel convergence, handoff ownership, deterministic-control separation, monotonic stream, and exact project-adapter AST boundary checks.

- [ ] Add acceptance tests using one fake public upstream agent across telegram, CLI, web, and omni with distinct sessions and same owner semantics.
- [ ] Add an AST scan restricted to `hermes_personal/gateway` and `plugins/hermes_personal`, rejecting semantic routing tables, forbidden provider/PI/VF imports, workflow mutation, and direct intelligence/factory calls.
- [ ] Run both new files and confirm RED only where production/fixtures remain incomplete.
- [ ] Complete scoped implementation and document identity, sessions, handoff, idempotency, replay, one brain, OperatorCommand controls, and deferred route cutover.

### Task 4: Gate Verification And Delivery

**Files:**
- Create ignored: `.superpowers/sdd/gate-2-task-6-report.md`

- [ ] Run `uv run pytest tests/hermes_personal/gateway tests/hermes_personal/contracts tests/hermes_personal/test_upstream_compatibility.py -q`.
- [ ] Run Ruff over every changed Python file and run `git diff --check`.
- [ ] Review the final diff against every acceptance/security criterion and remediate substantive findings with tests first.
- [ ] Write exact RED/GREEN/full-gate counts and concerns to the ignored report.
- [ ] Commit source, tests, and docs and report status plus full SHA.
