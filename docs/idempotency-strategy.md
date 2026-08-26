# Hermes Personal Idempotency Strategy

## Goals

Idempotency prevents duplicate inference, workflow transitions, budget charges,
provider work, and artifact publication when a client retries after timeout or
disconnect. It does not make different payloads equivalent and does not replace
optimistic concurrency.

## Agent turns

### Scope and key

The durable uniqueness scope is:

```text
(owner_user_id, idempotency_key)
```

Clients should generate a stable opaque key per logical user action and reuse it
for every retry. When omitted, `AgentTurnRequest` defaults the key to the
generated `turn_id`, which protects only retries that preserve that request
object.

### Semantic digest

The repository converts the request to primitives, removes `turn_id`,
`occurred_at`, and `idempotency_key`, serializes compact JSON with sorted keys,
and stores its SHA-256 digest. All remaining fields, including principal,
message, attachments, history, toolsets, workflow, locale, and channel
capabilities, are semantic.

### Claim outcomes

| Existing row | Digest | Status | Result |
| --- | --- | --- | --- |
| none | any | N/A | Insert `in_progress`, execute once |
| yes | different | any | raise `IdempotencyConflict` |
| yes | same | `in_progress` | raise `TurnInProgress` with canonical turn ID |
| yes | same | `completed`/`failed` | replay exact stored events in sequence |

Claim uses `BEGIN IMMEDIATE` so concurrent callers cannot both create the same
owner/key execution. Event uniqueness is `(turn_id, sequence)` plus globally
unique `event_id`.

## Budget reservations

### Scope and key

The durable uniqueness scope for budget reservations is:

```text
(owner_user_id, scope_id, idempotency_key)
```

### Semantic digest

The request calculates SHA-256 over `(owner_user_id, scope_id, channel, amount, currency)`.

### Claim & Lifecycle outcomes

- **Reserve Retry**:
  - Same key + same digest: returns existing `BudgetAllocation` without double deducting budget.
  - Same key + different digest: raises `BudgetConflict`.
- **Commit Retry**: Idempotent. Re-committing an already committed allocation updates local state and returns cleanly without double counting.
- **Release Retry**: Idempotent. Re-releasing an already released allocation returns cleanly without modifying balance. Releasing a committed allocation raises `BudgetError`.

## Workflow commands

The workflow repository stores `(workflow_id, command_id)` in
`processed_command`. Aggregate update, workflow events, processed commands, and
outbox records commit atomically. A duplicate command returns the current result
without applying another repository commit. The current engine nevertheless
commits before applying its transition and must be fixed before this storage
guarantee can be treated as end-to-end workflow correctness.

`expected_version` remains necessary. Idempotency answers "is this the same
command?"; versioning answers "was it based on the current aggregate?".

## Operator commands

`OperatorCommand.idempotency_key` defaults to `command_id`. The composable HTTP
route currently constructs a fresh command ID for each request and does not
accept a client command ID in its JSON mapping. Therefore network retries of
that route are not durably deduplicated unless the injected command handler adds
a stable target-level key. A production route should accept validated
`command_id`/`idempotency_key` fields and pass them unchanged.

## Budgets

`BudgetAllocation` carries an idempotency key, but the current in-memory engine
checks it only during commit. Calling `reserve_budget` twice creates two pending
allocations and is not exactly-once. Success commits an allocation and failure
releases it; neither state survives restart. A production implementation must
atomically claim/reuse the logical reservation before provider calls.

## Product-video jobs

Handlers use a process-local result cache keyed by workflow, stage, and
idempotency data. This protects duplicate dispatch in one process but is not
restart-durable. Durable production execution must persist job claims and
results before external side effects.

Recommended key form:

```text
product-video:<workflow_id>:<stage>:<workflow_version>:<input_digest>
```

The key must change when the workflow version or semantic input digest changes.
Artifact outputs should be reconciled by immutable artifact ID, version, and
digest before any retry.

## Artifact and binding stability

Canonical JSON hashing sorts object keys, so semantically identical resource
packs produce the same SHA-256 digest regardless of dictionary insertion order.
The legacy binding shim delegates this computation to the canonical binding
service.

Replacing an artifact is a new binding version, not a mutation under the old
version. Descendant invalidation makes stale approvals and output refs unusable.

## External provider requirements

When live providers are added:

- send the Hermes logical key through the provider's idempotency header when
  supported;
- persist provider request ID before polling;
- on timeout, query/reconcile provider status before creating another job;
- map webhook events by provider event ID and reject duplicate signatures/events;
- never generate a new key merely because an HTTP attempt number changed;
- include owner/workflow scope so one tenant cannot collide with another.

## Failure and cleanup rules

- A terminal failed turn remains replayable under its original key.
- A different semantic request requires a new key.
- Never delete an in-progress claim merely to unblock a retry without first
  proving the original execution cannot still produce side effects.
- Stale-claim recovery must use a lease/heartbeat and transition atomically.
- Retain idempotency records at least as long as any external side effect can be
  observed or retried.

## Test matrix

Every new idempotent operation should test:

1. same key and same payload executes once;
2. same key and reordered JSON maps to the same digest where order is semantic-free;
3. same key and different payload conflicts;
4. concurrent claims produce one owner;
5. in-progress duplicate does not start work;
6. completed and failed results replay exactly;
7. owner scope prevents cross-tenant collision;
8. restart recovery does not repeat external side effects;
9. version/digest changes produce a new valid operation;
10. timeout reconciliation happens before retry.
