# Personal review rework implementation plan

> For agentic workers: execute with executing-plans / bounded independent workers, with regression verification per component.

**Goal:** Correct the September 8 review findings and replace unsupported completion claims with reproducible offline evidence.

**Architecture:** Preserve the canonical upstream AIAgent and HermesTurnService wire facade. SQLite owns approvals, workflow/outbox, paid dispatch intent and recovery. Video Factory consumes bound approval receipts; operator decisions never call a private MCP singleton after committing.

**Tech stack:** Python, SQLite, pytest, Ruff, native PowerShell.

## Constraints

- Preserve pre-existing dirty work; no paid providers, real user data, live messaging, or Git history changes.
- Retain five HITL gates, explicit creative inputs, owner and artifact version binding.
- Tests use temporary databases and offline provider doubles at external boundaries.

## Work sequence

- [x] Regression tests for export initialization, completed-render settlement, missing/foreign reservation, and approval binding. Run focused pytest before fixes.
- [x] Fix workflow paid reservation ownership, durable replay and failure classification; propagate shared reservation to VF.
- [x] Replace operator private service calls with durable approval receipts delivered to the next job; validate owner/project/workflow/artifact/version before decision.
- [x] VF: exact gate verification, honest PI input transfer, durable provider state, authenticated resume, approved-file export binding.
- [x] Learning: approved bound receipt required; no self-approval or absent-service bypass; offline regressions.
- [x] Runtime: real discovery/snapshot readiness and fail-closed exec probes; assess session lifecycle against canonical contract.
- [x] Focused integration tests, then broader hermes_personal suite and Ruff. Record actual failures and limitations.
- [x] Repair malformed architecture document and reconcile current review status and handoff evidence.

## Acceptance commands

`uv run --no-sync pytest tests/hermes_personal -q`

`uv run --no-sync pytest tests/mcp_servers/test_video_factory_server.py -q`

`uv run --no-sync ruff check hermes_personal tests/hermes_personal`

`git diff --check`

Each finding closes only with source-level correction and relevant passing behavior tests. Offline evidence is not live-provider acceptance.
