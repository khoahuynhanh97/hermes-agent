# Hermes Personal Gateway Operations & Acceptance Guide

This document defines the operational procedures, offline acceptance evidence, and verified security invariants for the Hermes Personal Gateway runtime.

---

## 1. Supervised Runtime Architecture (`hermes start`)

The Hermes Personal Gateway runtime unifies all natural-language channels (`Telegram`, `CLI`, `Web`, `Omni`) through a single upstream Agent Turn boundary (`HermesTurnService`).

### Supervised Components
- **CLI Supervisor Entrypoint (`hermes start`)**:
  - Arguments:
    * `--mode {development,production}` (defaults to config-defined or development mode)
    * `--config CONFIG` (path to `config.yaml`)
    * `--no-open-browser` (suppresses browser launch in development mode)
  - Manages process topology: Gateway, Application API (FastAPI), MCP Discovery, Background Worker.
  - Implements bounded exponential backoff restarts for degraded child processes.
- **FastAPI Application Plane (`hermes_personal/application/`)**:
  - `/health/live`, `/health/ready`, `/health/components/{name}`
  - `/api/events` (SSE stream with monotonic sequence resumption)
  - `/api/events/replay` (cursor-based JSON event history)
  - `/api/operator/command` (authenticated operator action dispatcher)
  - `/api/artifacts/{id}` (canonical artifact metadata with owner isolation)
- **Shared Application Plane**:
  - `HermesTurnService`: Single natural-language turn boundary with global identity resolution.
  - `WorkflowEngine` & `ApprovalEngine`: Deterministic workflow execution and multi-stage human-in-the-loop approvals.
  - `CapabilityCatalogService` & `CapabilitySnapshotRepository`: Stable capability snapshot resolution with policy checks.
  - `DurableEventStore`: Commits all turn/workflow/approval/artifact events per owner.

---

## 2. Offline Verification & Operational Smoke Procedure (Zero Paid Provider Calls)

To verify end-to-end operation locally without paid external API calls:

1. **Start Runtime in Development Mode with Fake Profile**:
   ```bash
   uv run hermes start --mode development --no-open-browser
   ```
2. **Verify Liveness and Readiness Probes**:
   ```bash
   curl -i http://127.0.0.1:8000/health/live
   curl -i http://127.0.0.1:8000/health/ready
   ```
   Expected: HTTP 200 `{"status": "ready", "ready": true}` once all mandatory dependencies pass startup checks.

3. **Subscribe to SSE Event Stream**:
   ```bash
   curl -N http://127.0.0.1:8000/api/events?owner_id=op_admin
   ```
   Observe real event frames (`text_delta`, `tool_activity`, `workflow_state`, `heartbeat`) streamed with monotonic sequence IDs.

4. **Stop Runtime Cleanly**:
   Send `SIGINT` (Ctrl+C). Verify supervisor terminates all child processes cleanly without orphaned processes or corrupt database leases.

---

## 3. Security Boundaries and Operational Guardrails

- **Owner Isolation**: Events, workflows, artifacts, and learning candidates are strictly scoped to `owner_user_id`. Cross-user access returns HTTP 403 / None.
- **Optimistic Concurrency**: Operator approvals require matching `expected_version`; stale or duplicate submissions are rejected safely (`VersionConflict`).
- **Secret Redaction**: API keys, bearer tokens, passwords, and sensitive query parameters are redacted before logging or metric reporting.
- **Zero Fake Progress**: Frontend UI and backend services emit progress only from durable committed `AgentEvent` records. Synthetic progress timers and mock artifact IDs are strictly forbidden.

---

## 4. Packaging and Distribution Policy

Upstream Hermes enforces a packaging policy where unmanaged `uv build --wheel` is intentionally blocked by `setup.py` (`RuntimeError: Building wheels or sdists for hermes-agent is not supported. Hermes is distributed via shell installer, Docker, or Nix.`).

For development and testing:
- **Editable Development Install**:
  ```bash
  uv sync
  # or: uv pip install -e .
  ```
- **Nix / CI Build Verification**:
  ```bash
  $env:HERMES_NIX_BUILD="1"; uv build --wheel
  ```
