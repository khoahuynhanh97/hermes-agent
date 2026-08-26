# Hermes Personal Error Handling

## Error envelope

Capability failures use `CapabilityError` with stable `code`, human-readable
`message`, `retryable`, optional `capability_id`, actionable recovery, and
redacted `details`. General turn exceptions become terminal `failed`
`AgentEvent`s. Callers branch on code/type and retryability, never message text.

## Error classes

| Category | Examples | Retry policy |
| --- | --- | --- |
| Contract | unsupported schema, blank ID, invalid digest, bad payload | Do not retry unchanged input |
| Authentication/authorization | unknown identity/session, owner/channel mismatch, missing handoff | Re-authenticate or correct mapping; no automatic retry |
| Idempotency | key conflict, canonical turn still running | Conflict: new key/correct request; running: poll/replay later |
| Optimistic concurrency | workflow/binding `VERSION_CONFLICT` | Reload current version, reconcile, retry with same logical command semantics |
| HITL/precondition | `HITL_APPROVAL_REQUIRED`, `unmet_precondition` | Wait for explicit human action |
| Capability policy | unavailable binding, unauthorized skill/workflow, budget exceeded | Follow actionable recovery; do not blind retry |
| Budget accounting | `BudgetError`, `BudgetConflict` (idempotency key reused with mismatched payload) | Fail closed. Conflict requires new idempotency key or matching parameters. |
| Outbox delivery | Stale lease ACK (`StaleLeaseError`/`LeaseExpired`), max attempts exceeded | Reject stale ACK; exponential backoff on transient failure (`next_attempt_at`); poison message transition to `quarantined` state and operator requeue (`requeue_quarantined`) |
| Input integrity | `DIGEST_MISMATCH`, missing input ref, foreign artifact owner | Reconcile refs; no retry unchanged input |
| Transient provider/stage | PI/VF `*_FAILED` marked retryable | Retry within bounded budget with same idempotency key |
| Startup | `*_FAILED`, no readiness report/probe | Keep ingress closed; repair dependency, rerun startup |
| Process | child exit/restart exhaustion | Supervisor backoff; required exhaustion stops runtime |

## Capability policy codes

Current stable codes include:

- `unauthenticated`
- `capability_id_mismatch`
- `unauthorized_skill`
- `unauthorized_workflow`
- `binding_unavailable`
- `schema_version_mismatch`
- `post_execution_review_required`
- `unmet_precondition`
- `budget_exceeded`
- `degraded_capability_warning`
- `degraded_policy_denied`
- `tool_not_found`
- `schema_unavailable`

Discovery diagnostics also include `duplicate_wire_ownership`, `check_failed`,
and `schema_incompatible`.

## Product-video codes

| Code | Retryable intent |
| --- | --- |
| `WORKFLOW_NOT_FOUND` | no; fix workflow reference |
| `HITL_APPROVAL_REQUIRED` | no automatic retry; wait for approval |
| `ILLEGAL_WORKFLOW_STATE` | no; reconcile state |
| `VERSION_CONFLICT` | reload and reconcile |
| `DIGEST_MISMATCH` | no; replace stale input |
| `INVALID_INPUT`, `MISSING_INPUT_REF` | no; correct payload |
| `PI_RESEARCH_FAILED`, `PI_PACK_FAILED`, `PI_LOCK_FAILED` | marked retryable |
| `VF_BRIEF_FAILED`, `VF_SCENE_FAILED`, `VF_STORYBOARD_FAILED` | marked retryable |
| `VF_RENDER_FAILED`, `VF_EXPORT_FAILED` | marked retryable |

## Retry ownership

Retry must be owned by exactly one layer for a given operation:

- process restart: `Supervisor`;
- in-process job attempt: `JobDispatcher`;
- provider request: future provider adapter;
- user command replay: idempotency repository;
- workflow recovery: persisted aggregate/outbox recovery.

Do not stack retries at every layer. Bound attempts, elapsed time, and cost; carry
the same logical idempotency key across retry attempts.

## Backoff behavior

`Supervisor` implements exponential backoff:

```text
delay = min(base_backoff_seconds * 2^attempt_index, max_backoff_seconds)
```

Attempts are limited within a time window. Required-process exhaustion makes the
runtime unavailable; optional processes become degraded.

`JobDispatcher` currently retries immediately with no delay or jitter. Its
timeout helper cannot kill a running Python thread. Consequently:

- keep handlers bounded and cooperative;
- default to zero retries unless the operation is idempotent;
- do not use it as a substitute for a durable worker pool;
- never launch a second paid action after timeout without reconciliation.

Any future provider retry should use capped exponential backoff with jitter,
honor `Retry-After`, and retry only transport failures, selected 429/5xx errors,
or explicitly retryable provider codes.

## Recovery and outbox

Workflow commit writes aggregate, event, processed command, and outbox message in
one SQLite transaction.

The durable outbox mechanism (`WorkflowRecoveryService`) provides at-least-once delivery guarantees:
- **Outbox State Machine**: Messages transition `pending` -> `leased` -> deleted (on successful ACK) or `quarantined` (upon reaching max attempt threshold).
- **Atomic Conditional Claim**: Workers claim pending or expired-lease items via conditional SQL update (`UPDATE workflow_outbox SET status = 'leased', worker_id = ?, lease_token = ?, leased_at = datetime('now'), lease_expires_at = datetime('now', '+30 seconds'), attempt_count = attempt_count + 1 WHERE outbox_id = ? AND (status = 'pending' OR (status = 'leased' AND lease_expires_at < datetime('now'))) AND (next_attempt_at IS NULL OR next_attempt_at <= datetime('now'))`), populating worker ID and lease token.
- **Stale Lease ACK Rejection**: `ack_outbox(outbox_id, lease_token)` verifies that the provided `lease_token` matches the current active lease. If a lease expires and is re-leased to another worker, a stale ACK attempt is rejected with a `StaleLeaseError` / `LeaseExpired` exception to prevent premature or duplicate row deletions.
- **Bounded Exponential Backoff**: Processing failures schedule retries by setting `next_attempt_at = now + min(base_delay * 2^(attempt_count - 1), max_delay)`. Workers ignore items whose backoff window has not elapsed.
- **Poison Message Quarantine & Recovery**: When `attempt_count` reaches `max_attempts` (default 5), the record moves to `quarantined` status to isolate poison messages. Operators inspect quarantined messages and execute `requeue_quarantined(outbox_id)` to clear error logs, reset attempt counters to 0, and transition status back to `pending` for re-execution.

The generic `WorkflowEngine` also commits before transition validation and has an
inconsistent `job_succeeded` mapping. Until corrected, an illegal transition may
leave a persisted event/version and recovery may load stale aggregate state.
Operators must inspect both aggregate and event history during reconciliation.

## DLQ policy

There is no DLQ in the current implementation. Documentation and dashboards must
say "workflow outbox" or "failed job" rather than DLQ.

Before adding a DLQ, define:

- the broker and delivery guarantee;
- retry-exhaustion threshold and reason envelope;
- original message, digest, owner, workflow, and correlation metadata;
- secret/content redaction and retention;
- replay authorization and idempotency behavior;
- operator inspection and purge controls.

## HTTP error behavior

| Status | Current use |
| --- | --- |
| 400 | bad target or command handler failure |
| 403 | failed token validation or foreign artifact |
| 404 | missing artifact |
| 503 | not live, not ready, missing probe, unavailable component |

The HTTP layer currently returns compact ad hoc error bodies rather than the
full `CapabilityError` schema. New routes should map domain codes consistently
and avoid exposing raw exception details in production.

## Logging and redaction

Log correlation IDs and stable error codes. Do not log tokens, authorization
headers, cookies, passwords, private keys, full provider payloads, or sensitive
user content. Apply recursive redaction before emitting structured errors,
supervisor events, startup reports, or telemetry.
