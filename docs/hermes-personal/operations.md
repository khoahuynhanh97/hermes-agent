# Hermes Personal Gateway Operations & Acceptance Guide

This document defines the operational procedures, smoke test verifications, and offline acceptance evidence for the Hermes Personal Gateway runtime.

---

## 1. Overview of Supervised Runtime Architecture

The Hermes Personal Gateway runtime coordinates 4 core ingress channels (`Telegram`, `CLI`, `Web`, `Omni`) through one upstream Agent Turn boundary (`HermesTurnService`).

### Key Runtime Components
- **CLI Supervisor (`hermes start`)**: Manages role discovery, validation, readiness probe polling, child process supervision, and graceful shutdown.
- **FastAPI Application Layer (`hermes_personal/application/`)**:
  - `/health/live`, `/health/ready`, `/health/components/{name}`
  - `/api/events` (durable SSE streaming with monotonic sequence resume)
  - `/api/events/replay` (cursor-based JSON event history)
  - `/api/operator/command` (authenticated operator action dispatcher)
  - `/api/artifacts/{id}` (canonical artifact metadata with owner isolation)
- **Shared Application Plane**:
  - `HermesTurnService`: Single natural-language turn boundary.
  - `WorkflowEngine` & `ApprovalEngine`: Deterministic workflow execution and multi-stage human-in-the-loop approvals.
  - `CapabilityCatalog` & `ActiveSnapshotPointer`: Stable capability snapshot resolution with tool search.
  - `DurableEventStore`: Commits all turn/workflow/approval/artifact events per owner.

---

## 2. Offline Smoke Verification Procedure (Zero Paid Provider Calls)

To verify end-to-end operation locally without paid external API calls:

1. **Start Runtime in Development Mode with Fake Profile**:
   ```bash
   uv run hermes start --mode development --host 127.0.0.1 --port 8000
   ```
2. **Verify Liveness and Readiness**:
   ```bash
   curl -i http://127.0.0.1:8000/health/live
   curl -i http://127.0.0.1:8000/health/ready
   ```
   Expected: HTTP 200 `{"status": "ready", "ready": true}` once all mandatory dependencies pass startup checks.

3. **Submit an Agent Turn via Omni Ingress**:
   ```bash
   curl -i -X POST http://127.0.0.1:8000/api/turn \
     -H "Content-Type: application/json" \
     -d '{"principal_id": "op_admin", "channel": "omni", "text": "Research market trends for AI audio"}'
   ```
4. **Subscribe to SSE Event Stream**:
   ```bash
   curl -N http://127.0.0.1:8000/api/events?owner_id=op_admin
   ```
   Observe real event frames (`text_delta`, `tool_activity`, `workflow_state`, `heartbeat`) streamed with monotonic IDs.

5. **Stop Runtime Cleanly**:
   Send `SIGINT` (Ctrl+C). Verify supervisor terminates all child processes cleanly without orphaned processes or corrupt database leases.

---

## 3. Security Boundaries and Operational Guardrails

- **Owner Isolation**: Events, workflows, artifacts, and learning candidates are strictly scoped to `owner_user_id`. Cross-user access returns HTTP 403 / None.
- **Optimistic Concurrency**: Operator approvals require matching `expected_version`; stale or duplicate submissions are rejected safely.
- **Secret Redaction**: API keys, bearer tokens, passwords, and sensitive query parameters are redacted before logging or metric reporting.
- **Zero Fake Progress**: Frontend UI and backend services emit progress only from durable committed `AgentEvent` records. Synthetic progress timers and mock artifact IDs are strictly forbidden.

---

## 4. Packaging and Wheel Build Verification

Build canonical distribution wheel:
```bash
uv build --wheel
```
Verify CLI help entrypoint:
```bash
uv run hermes start --help
```
