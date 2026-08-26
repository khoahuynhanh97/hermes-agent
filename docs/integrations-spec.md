# Hermes Personal Integration Specification

## Implementation status legend

- **Implemented**: importable source exists and focused tests exercise it.
- **Composable**: service exists but production authentication/storage/wiring must
  be injected.
- **Declared only**: present in a topology or cutover inventory without a mounted
  production entry point.

## HTTP application

The canonical Gateway composition is
`hermes_personal.runtime.gateway_server.create_gateway_application`; its router
factory is `hermes_personal.application.app.create_application`. The public App
API at `hermes_personal.api.server` authenticates a process-lifetime browser
session and forwards the owner-bound Gateway key over loopback. Direct Gateway
compatibility query/body `auth_token` input remains internal-only; new clients
use `Authorization: Bearer <token>` or the App API cookie.

No application-level rate limiter is implemented. Deployments must enforce
request rate, connection count, body size, and SSE limits at a trusted edge until
equivalent application controls exist.

### Health API

| Method/path | Auth | Success | Failure |
| --- | --- | --- | --- |
| `GET /health/live` | none | `200 {status: ok, live: true}` | `503` when probe marks process not live |
| `GET /health/ready` | none | `200` with readiness details | `503`, including `NO_READINESS_PROBE` or startup failure code |
| `GET /health/components/{name}` | none | `200` for healthy/degraded | `503` for unavailable/no probe |

Health responses must not expose secrets, raw credentials, or sensitive
dependency payloads.

### Event replay

`GET /api/events/replay`

Query parameters:

| Name | Type | Default |
| --- | --- | --- |
| `owner_id` | string | required |
| `after_seq` | integer | `0` |
| `limit` | integer | `100` |
| `auth_token` | string | direct-Gateway compatibility only |

Success response:

```json
{
  "events": [
    {
      "event_id": "evt_123",
      "cursor": 2,
      "event_type": "completed",
      "principal_id": "owner-7",
      "session_id": "session-9",
      "turn_id": "turn-4",
      "sequence": 2,
      "data": {"final_response": "Done"},
      "workflow_id": null,
      "job_id": null,
      "approval_id": null,
      "occurred_at": "2026-08-26T03:00:00+00:00"
    }
  ],
  "next_cursor": 2,
  "count": 1
}
```

`cursor` and `next_cursor` are owner-global offsets allocated transactionally
with each durable event. They are distinct from `AgentEvent.sequence`, which is
turn-scoped. The cursor survives SQLite reopen and is safe for multi-turn resume.
`after_seq` must be non-negative and `limit` is bounded to `1..500`.

### Server-sent events

`GET /api/events` uses the same `owner_id`, `after_seq`, token inputs and returns
`text/event-stream`. Committed events are emitted as:

```text
id: 2
event: completed
data: {"event_id":"evt_123", ...}

```

The generator emits the currently available events, then one separate
`heartbeat` frame and ends. It is not a permanent broker subscription; clients
reconnect with the last durable cursor.

### Operator command

`POST /api/operator/command`

```json
{
  "owner_id": "owner-7",
  "command_type": "approve",
  "target_id": "approval-8",
  "expected_version": 3,
  "payload": {}
}
```

Supported command types: `approve`, `reject`, `retry`, `cancel`, `upload`, and
`form_update`. A configured handler returns `200 {status: ok, command_id,
result}`. Without a handler, the current composable API returns `accepted`; this
does not mean a durable command was processed.

Unknown command types are rejected before the configured handler. Replay cursor
and limit bounds are enforced at both the HTTP and service boundaries. Request
body size and application-level rate limits remain an edge/deployment control.

### Artifact metadata

`GET /api/artifacts/{artifact_id}?owner_id=<owner>` returns immutable metadata
only when the authenticated owner matches the artifact owner. Responses are 404
for missing artifacts and 403 for authentication or foreign ownership.

## Natural-language turn routes

`POST /api/turn` and `POST /api/omni/turn` accept:

```json
{
  "conversation_id": "chat-42",
  "message": "Summarize the approved product research"
}
```

The authenticated owner and external subject come from the credential, never
from caller-supplied ownership fields. `Idempotency-Key` is optional but strongly
recommended. Success is a newline-delimited stream of canonical `AgentEvent`
objects ending in `completed` or `failed`. The service persists each event to
SQLite before yielding it to the client. If the upstream iterator ends without
a terminal event, the Gateway emits and persists a structured failure.

## Upstream AIAgent integration

`UpstreamAIAgentAdapter` is the canonical public-contract adapter for an already
constructed upstream `AIAgent`. The configured runtime initializes the public
`AIAgent` with upstream configuration and invokes `AIAgent.run_conversation`,
mapping streaming deltas and tool activity into `AgentEvent`. The fake runtime
emits deterministic streaming deltas for offline development and smoke tests.

Adapters must not call private agent-loop internals or create a second planner.

## MCP and capability integrations

MCP discovery converts configured server tools into governed implementation
bindings. A binding is usable only when its stable capability ID, wire ownership,
schema versions, health, and active snapshot pass discovery and policy checks.

External MCP authentication and rate limits are server-specific configuration;
they are not hard-coded in `CapabilityDescriptor`. Secrets remain in environment
or provider configuration and never enter catalog snapshots.

## Product Intelligence and Video Factory

The current clients under `hermes_personal/integrations/` are deterministic local
contract implementations:

- `ProductIntelligenceClient`: research, resource-pack creation, and lock refs;
- `VideoFactoryClient`: brief, scene plan, storyboard, render, and export refs.

They perform no external HTTP calls, have no auth headers, and have no provider
rate limits. Their digest/artifact output supports offline workflow tests; it is
not evidence of a live provider integration.

The compatibility package `hermes_personal/integrations/product_video/`
delegates to the canonical `hermes_personal/product_video/` service and must not
duplicate hashing or invalidation logic.

## Adding a live provider

A live integration specification must add:

1. base URL and API version ownership;
2. authentication mechanism and rotation procedure;
3. request/response schemas and provider error mapping;
4. connect/read/overall timeouts;
5. documented provider rate limits and local throttling behavior;
6. retry eligibility and `Retry-After` handling;
7. idempotency headers/keys and reconciliation API;
8. webhook verification, ordering, and replay protection when applicable;
9. fake-provider tests with no paid calls;
10. migration, rollback, observability, and data-retention notes.
