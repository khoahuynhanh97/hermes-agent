# Hermes Personal Integration Specification

## Implementation status legend

- **Implemented**: importable source exists and focused tests exercise it.
- **Composable**: service exists but production authentication/storage/wiring must
  be injected.
- **Declared only**: present in a topology or cutover inventory without a mounted
  production entry point.

## HTTP application

The FastAPI factory is `hermes_personal.application.app.create_application`.
It mounts the health and events routers below. Authentication accepts
`Authorization: Bearer <token>`; compatibility query/body `auth_token` is also
accepted. Production must inject a real owner-bound validator as described in
[Security and auth](security-and-auth.md#http-authentication).

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
| `auth_token` | string | empty; prefer Bearer header |

Success response:

```json
{
  "events": [
    {
      "event_id": "evt_123",
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

The cursor is the last returned event sequence in the current store interface.
However, `AgentEvent.sequence` is scoped to a turn and restarts at zero; it is not
an owner-global offset. The in-memory API store therefore cannot provide correct
multi-turn cursor replay. Production must introduce a durable owner-global cursor
and test resume across interleaved turns before clients rely on `next_cursor`.

### Server-sent events

`GET /api/events` uses the same `owner_id`, `after_seq`, token inputs and returns
`text/event-stream`. Committed events are emitted as:

```text
id: 2
event: completed
data: {"event_id":"evt_123", ...}

```

The current generator emits all available events, then one separate `heartbeat`
frame and ends. It is not a permanent broker subscription, and it shares the
per-turn cursor limitation above.

### Operator command

`POST /api/operator/command`

```json
{
  "owner_id": "owner-7",
  "command_type": "approve",
  "target_id": "approval-8",
  "expected_version": 3,
  "payload": {},
  "auth_token": "compatibility-only"
}
```

Supported command types: `approve`, `reject`, `retry`, `cancel`, `upload`, and
`form_update`. A configured handler returns `200 {status: ok, command_id,
result}`. Without a handler, the current composable API returns `accepted`; this
does not mean a durable command was processed.

Known validation gap: `OperatorCommandType` is a static `Literal`, but the
dataclass does not perform a runtime membership check. The raw HTTP route can
therefore pass an unknown command string to a configured handler. Production
wiring must validate the enum and bound `after_seq`, `limit`, and request size.

### Artifact metadata

`GET /api/artifacts/{artifact_id}?owner_id=<owner>` returns immutable metadata
only when the authenticated owner matches the artifact owner. Responses are 404
for missing artifacts and 403 for authentication or foreign ownership.

## Declared but not mounted routes

The cutover inventory declares `/api/turn` and `/api/omni/turn`. The current
FastAPI factory does not mount them. Do not send clients to these routes or mark
Web/Omni turn ingress production-ready until a router converts authenticated
input to `AgentTurnRequest` and calls `HermesTurnService` with durable stores.

## Upstream AIAgent integration

`UpstreamAIAgentAdapter` is the only general-purpose reasoning integration. It
uses the public `AIAgent.run_conversation` contract, translates streaming text
and tool activity into `AgentEvent`, and requires the final result fields
`final_response`, `messages`, and `completed`.

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
