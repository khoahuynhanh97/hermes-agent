# Hermes Personal Business Logic

## Canonical routing rules

| Input | Condition | Route | Reject when |
| --- | --- | --- | --- |
| Natural-language message | Authenticated channel identity and valid session | `HermesTurnService` | Unknown identity/session, owner mismatch, channel mismatch |
| Workflow continuation | Session owns active workflow or explicit handoff exists | Same canonical turn service with `workflow_id` | Foreign owner or missing handoff |
| Capability call | Active snapshot resolves ID and policy allows it | Bound implementation | Unknown/unavailable binding or denied policy |
| Operator action | Authenticated owner, supported command, expected version | Command handler/workflow service | Bad target, forbidden owner, version conflict |
| Product-video job | Legal non-HITL state, expected workflow version and input digest | Stage handler | Waiting approval, illegal state, stale version/digest |
| Learning retrieval | Approved and active learning version | Context assembler | Candidate is pending, rejected, rolled back, or foreign |

Channels must not route around `HermesTurnService` for ordinary agent turns.
Channel-specific behavior is limited to authentication, normalization,
capability declaration, event rendering, and platform delivery.

## Turn decision matrix

| Check | Pass | Fail |
| --- | --- | --- |
| Contract schema and non-empty message/attachment | Continue | Validation error |
| `(channel, actor_id)` resolves | Load owner | Authorization failure |
| Session exists and owner/channel match | Continue | Authorization failure |
| Requested workflow is active or handed off | Continue | Authorization failure |
| `(owner, idempotency_key)` is new | Claim execution | See duplicate cases below |
| Same key and same digest is completed/failed | Replay exact committed events | N/A |
| Same key and same digest is running | Return in-progress failure | N/A |
| Same key and different digest | Reject conflict | Never overwrite prior execution |
| Approved learning assembler present | Add approved context | Use canonical history only |
| Agent emits event | Persist, project, then yield | Convert failure to terminal event |

## Capability policy matrix

The capability policy evaluates these gates in order. A denial returns a
structured `CapabilityError` with recovery guidance.

| Gate | Rule |
| --- | --- |
| Authentication | Context must be authenticated when the capability requires a principal |
| Identity | Requested capability ID must match the manifest/binding |
| Skill | Calling skill must be in `allowed_skills` when restricted |
| Workflow | Active workflow must be in `allowed_workflows` when restricted |
| Health | `unavailable` is denied; `degraded` is conditional |
| Approval | Enforce `none`, `review_required`, `approved_only`, `hitl`, or named precondition policy |
| Budget | Metered/paid calls require durable atomic budget reservation check (`BudgetRepository.reserve_budget`) |
| Degraded mode | Only low-risk, free, non-approval work may continue with a warning |

## Durable Budget Reservation Rules

All metered or paid operations require durable budget authorization managed by `BudgetRepository` in `hermes_personal/workflows/budgets.py`:

- **Atomic Reservation (`reserve_budget`)**: Executed inside a SQLite `BEGIN IMMEDIATE` transaction to atomically check total and per-channel budget limits (`total_used + amount <= max_total` and `channel_used + amount <= per_channel_limit`) before writing a new reservation with `state = 'reserved'`.
- **Idempotency & Replay**: Re-submitting an identical reservation request (`owner_user_id`, `scope_id`, `idempotency_key`, request digest) returns the existing `BudgetAllocation` record without double-deducting budget. A key reuse with mismatched parameters raises `BudgetConflict`.
- **Lifecycle & Deduplication**:
  - `commit_budget(alloc)` moves state to `'committed'`. Retrying commit is idempotent and does not double-count.
  - `release_budget(alloc)` moves state to `'released'`. Retrying release is idempotent. Releasing a committed allocation is forbidden.
- **Durable Persistence**: State survives process restarts via the SQLite `budget_reservation` table. Active (`reserved`) and `committed` allocations count toward total consumption; `released` allocations do not.
- **Fail Closed**: Database or backend failures during budget authorization immediately fail closed with `BudgetError`. Read-only `check_budget` operations do not mutate database state.

## Durable Outbox Delivery Rules

Workflow event notifications and side-effect messages require durable outbox delivery guarantees managed by `WorkflowRecoveryService` and `workflow_outbox` in SQLite:

- **Outbox State Machine**: Outbox items follow a strict state progression: `pending` -> `leased` -> deleted (upon successful acknowledgement) or `quarantined` (upon max attempt exhaustion).
- **Atomic Conditional Update Claim Strategy**: Workers claim pending or expired-lease outbox records atomically using conditional SQL updates (`UPDATE workflow_outbox SET status = 'leased', worker_id = ?, lease_token = ?, leased_at = datetime('now'), lease_expires_at = datetime('now', '+30 seconds'), attempt_count = attempt_count + 1 WHERE outbox_id = ? AND (status = 'pending' OR (status = 'leased' AND lease_expires_at < datetime('now'))) AND (next_attempt_at IS NULL OR next_attempt_at <= datetime('now'))`). This guarantees at-least-once delivery while preventing worker race conditions.
- **Stale Lease ACK Rejection**: Acknowledging a delivered outbox record (`ack_outbox`) requires matching `outbox_id` and the worker's active `lease_token`. If a lease expires and is re-claimed by another worker, any late ACK attempt using the stale lease token is rejected with a `StaleLeaseError` / `LeaseExpired` exception, preventing premature or double deletion.
- **Bounded Exponential Backoff**: Processing failures return the outbox item to unclaimed status with an updated `next_attempt_at` timestamp calculated using bounded exponential backoff (`min(base_delay * 2^(attempt_count - 1), max_delay)`). Workers skip items whose `next_attempt_at` is in the future.
- **Poison Message Quarantine & Requeue Procedure**: Items exceeding the maximum allowed attempt threshold (default 5 retries) transition to `quarantined` status to isolate poison messages and prevent infinite retry loops. Operators can inspect quarantined messages and execute `requeue_quarantined(outbox_id)` to reset message status to `pending`, clear error history, and reset `attempt_count` for safe manual reprocessing.

## Operator command rules

Supported command types are `approve`, `reject`, `retry`, `cancel`, `upload`,
and `form_update`. Every command carries:

- authenticated `PrincipalContext`;
- non-empty `target_id`;
- non-negative `expected_version` for optimistic concurrency;
- unique `command_id` and default idempotency key;
- immutable payload mapping.

The generic workflow repository deduplicates `(workflow_id, command_id)`.
Handlers must validate owner and expected version before side effects.

## Product-video decision matrix

| Stage | Legal source state | Required input | Next HITL/state |
| --- | --- | --- | --- |
| Research | `idle` | Product name, keywords, optional PDP URL | `researching` then product-lock preparation |
| Product lock | `researching`/stage-defined state | Resource-pack content | `AwaitingProductLock` |
| Build/brief | approved product lock | `lock_ref` with PI ownership and matching digest | `AwaitingBriefApproval` |
| Scene plan | approved brief | `brief_ref` with VF ownership and matching digest | `AwaitingSceneApproval` |
| Storyboard | approved scene plan | `scene_plan_ref` | `AwaitingStoryboardApproval` |
| Render | approved storyboard | `storyboard_ref` | `AwaitingFinalApproval` |
| Export | approved final render | `render_ref` | `completed` |

No job may dispatch while the workflow is in one of the five `Awaiting*`
states. Approval moves the workflow forward; rejection/revision returns to the
documented revision state.

## Artifact replacement and invalidation

The immutable dependency chain is:

```text
product_lock -> brief -> scene_plan -> storyboard -> render -> export
```

Replacing a node increments the binding version and clears every descendant.
Any pending or approved approval whose payload contains an exact descendant
`artifact_id` is changed to rejected. Matching is recursive and exact; for
example, `artifact-1` must not invalidate `artifact-10`.

Artifact ownership is enforced:

- `lock_ref`: `product_intelligence`;
- brief, scene plan, storyboard, render, export: `video_factory`.

## Budget rules

The product-video handlers currently reserve deterministic stage costs:

| Stage | Units |
| --- | ---: |
| Creative brief | 5 |
| Scene plan | 5 |
| Storyboard | 10 |
| Render | 50 |
| Export | 20 |

Reservation happens before work; success commits the reservation and failure
releases it. The current in-memory engine uses an idempotency key only to avoid a
second commit; it does not deduplicate repeated reservations and is not durable.
These units are internal policy values, not provider prices. Paid-provider
execution requires a durable reservation claim before it is safe for production.

## Governed learning

Task outcomes can propose learning candidates, but candidates are not injected
into future turns until evaluation and explicit approval publish an active
version. Retrieval is owner-scoped. Rollback changes the active version without
deleting evidence or history.

## Explicit non-behaviors

- No silent approval of product locks, creative milestones, final video, or
  learning publication.
- No direct external provider calls from deterministic test clients.
- No substring-based artifact invalidation.
- No cross-owner session or artifact access.
- No assumption that declarative cutover routes are mounted.
