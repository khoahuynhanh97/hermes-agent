# Hermes Personal Data Contracts

## Contract policy

Canonical wire contracts live in `hermes_personal/contracts/`. They are frozen
Python dataclasses, not Pydantic models. HTTP adapters must validate and convert
untrusted JSON before constructing them. All current contracts use
`schema_version = 1`; unsupported versions fail closed.

Timestamps are timezone-aware ISO 8601 values. Mapping fields are copied into
read-only mappings during construction. Identifiers are opaque strings; callers
must not parse business meaning from generated prefixes.

## PrincipalContext

| Field | Type | Rules |
| --- | --- | --- |
| `actor_id` | string | Non-blank authenticated channel subject |
| `owner_user_id` | string | Non-blank canonical owner |
| `channel` | enum | `telegram`, `cli`, `web`, `omni` |
| `session_id` | string | Non-blank canonical session |
| `roles` | string array | Metadata only; no complete RBAC enforcement |

## AgentTurnRequest

| Field | Type | Required/default |
| --- | --- | --- |
| `principal` | `PrincipalContext` | required |
| `message` | string | may be blank only when attachments exist |
| `schema_version` | integer | `1` |
| `attachments` | `AttachmentRef[]` | empty tuple |
| `conversation_history` | object array | empty; canonical service may replace with persisted history |
| `enabled_toolsets` | string array | empty |
| `workflow_id` | string/null | null |
| `locale` | string | `vi-VN` |
| `occurred_at` | datetime | current UTC; timezone required |
| `turn_id` | string | generated `turn_<uuidhex>` |
| `idempotency_key` | string | defaults to `turn_id` |
| `channel_capabilities` | `ChannelCapabilities` | all false unless normalizer sets them |

Example JSON representation:

```json
{
  "schema_version": 1,
  "principal": {
    "actor_id": "telegram-user-42",
    "owner_user_id": "owner-7",
    "channel": "telegram",
    "session_id": "session-9",
    "roles": []
  },
  "message": "Create a product video",
  "attachments": [],
  "conversation_history": [],
  "enabled_toolsets": ["product-video"],
  "workflow_id": "workflow-3",
  "locale": "vi-VN",
  "occurred_at": "2026-08-26T03:00:00Z",
  "turn_id": "turn_abc123",
  "idempotency_key": "client-request-123",
  "channel_capabilities": {
    "streaming": true,
    "interactive_controls": true,
    "attachments": true
  }
}
```

### AttachmentRef

| Field | Type | Rules |
| --- | --- | --- |
| `attachment_id` | string | non-blank |
| `kind` | enum | image/video/audio/document/other |
| `media_type` | string | adapter-supplied MIME type |
| `uri` | string | non-blank; storage policy validates scheme/root |
| `size_bytes` | integer/null | non-negative |
| `digest_sha256` | string/null | exactly 64 lowercase hex characters |

### ChannelCapabilities

Boolean fields: `streaming`, `interactive_controls`, and `attachments`.
Normalizer defaults currently enable streaming and attachments for all four
channels; interactive controls are enabled for Telegram, Web, and Omni but not
CLI.

## AgentEvent

| Field | Type | Rules |
| --- | --- | --- |
| `event_type` | enum | text_delta, clarification_required, tool_activity, workflow_state, approval_required, cost_update, artifact, warning, completed, failed |
| `principal_id` | string | canonical owner ID; non-blank |
| `session_id` | string | non-blank |
| `turn_id` | string | non-blank |
| `sequence` | integer | non-negative and unique within turn |
| `schema_version` | integer | `1` |
| `data` | object | immutable mapping copy |
| `workflow_id`, `job_id`, `approval_id`, `tool_call_id` | string/null | correlation IDs |
| `occurred_at` | datetime | timezone-aware |
| `event_id` | string | generated `evt_<uuidhex>`, globally unique in SQLite |

Every successful turn must terminate with `completed`; handled failures terminate
with `failed`. Events are persisted before delivery and duplicate completed turns
replay the original events.

`sequence` is monotonic only within one `turn_id`. APIs that need an owner- or
session-wide replay cursor must allocate a separate durable global offset.

## OperatorCommand

| Field | Type | Rules |
| --- | --- | --- |
| `principal` | `PrincipalContext` | required |
| `command_type` | enum | approve/reject/retry/cancel/upload/form_update |
| `target_id` | string | non-blank |
| `expected_version` | integer | non-negative |
| `schema_version` | integer | `1` |
| `payload` | object | immutable mapping copy |
| `occurred_at` | datetime | timezone-aware |
| `command_id` | string | generated `cmd_<uuidhex>` |
| `idempotency_key` | string | defaults to `command_id` |

## CapabilityDescriptor

Required identity fields are `capability_id`, `wire_name`, `owner`, `version`,
`input_schema_version`, and `output_schema_version`. Governance fields are:

| Field | Allowed values |
| --- | --- |
| `source` | native/plugin/hermes_mcp/external_mcp |
| `trust` | first_party/configured_external/untrusted |
| `side_effects` | read/write/external/paid |
| `principal_mode` | session/server/none |
| `idempotency` | required/supported/none |
| `risk` | low/medium/high/critical |
| `cost_class` | free/metered/paid |
| `health` | unknown/healthy/degraded/unavailable |

The descriptor also carries toolset, approval/data/provider policies and skill/
workflow allowlists. `capability_id` is stable; `wire_name` may be rebound in a
new catalog snapshot.

## CapabilityError

Serialized failures contain:

```json
{
  "code": "budget_exceeded",
  "message": "Capability requires cost authorization",
  "retryable": false,
  "capability_id": "video.render",
  "actionable_recovery": "Allocate positive budget before calling capability",
  "details": {}
}
```

Serialization recursively redacts secret-bearing keys and values. Callers should
branch on `code` and `retryable`, not parse `message`.

## Product-video contracts

`ArtifactRef` fields are `artifact_id`, positive `version`, digest prefixed by
`sha256:`, and owner `product_intelligence` or `video_factory`.

`ProductVideoBinding` fields are `product_id`, positive monotonic `version`, and
optional refs `lock_ref`, `brief_ref`, `scene_plan_ref`, `storyboard_ref`,
`render_ref`, `export_ref`. Mutations return a new binding and clear stale
descendants.

## Compatibility and evolution

- Additive optional fields may retain schema version 1 when old consumers safely
  ignore them.
- Required-field, semantic, enum, or idempotency changes require a new schema
  version and explicit adapter support.
- Persisted events are immutable. Migrations add projections/read adapters rather
  than rewriting historical payloads.
- Compatibility shims delegate to canonical services and must not duplicate
  hashing or workflow logic.
