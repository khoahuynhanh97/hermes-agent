# Hermes Personal Workflow Implementation

This note identifies the workflow abstractions that actually exist. Canonical
rules live in [Architecture](../architecture.md),
[Business logic](../business-logic.md), and
[Idempotency](../idempotency-strategy.md).

## Three distinct layers

Do not treat these layers as one state machine:

1. `WorkflowAggregate` in `models.py` is a declarative definition object with
   states, transitions, optional artifact-slot metadata, and approval metadata.
2. `WorkflowEngine` in `engine.py` is the implemented generic command/event
   engine with its own compact state map.
3. `ProductVideoWorkflowState` and helpers in `product_video/` implement the
   domain-specific 14-state HITL pipeline.

The generic engine does not currently execute the `required_artifacts` or
`approval_required` metadata from `WorkflowAggregate`. Domain handlers enforce
product-video state, version, digest, budget, and HITL checks.

## Declarative definitions

`definitions.py` contains definitions named `product_to_video`,
`product_research`, `knowledge_learning`, `hook_cta_learning`, and
`video_deconstruction`. They are planning/validation data. The canonical
product-video execution state is the separate implementation under
`hermes_personal/product_video/`.

## Generic workflow engine

Commands require `command_id` and `type`, with optional `workflow_id` and `args`.
The intended engine responsibilities are:

- checks duplicate `(workflow_id, command_id)`;
- derives one workflow event;
- atomically commits aggregate/version, events, processed command IDs, and
  outbox rows through `WorkflowRepository`;
- validates its implemented transition map;
- raises version conflicts instead of overwriting concurrent state.

The current engine keeps an in-memory aggregate cache backed by repository reads,
but it calls `commit_workflow()` with the pre-transition aggregate and only then
applies/validates the transition in memory. This can persist an event/version for
an invalid command and leave recovered state stale. In addition,
`job_succeeded` maps to `job_dispatched` while the allowed-state table expects a
target named `job_succeeded`, so that command is rejected from the documented
job states. These are implementation defects, not supported behavior.

## Persistence

SQLite tables are `workflow`, `workflow_event`, `processed_command`, and
`workflow_outbox` (which supports worker lease tokens, expiration tracking, retry counters, backoff timestamps, and quarantine states). `WorkflowRepository.commit_workflow()` owns the transaction.
Never write these tables independently from business handlers.

## Approvals

`ApprovalService` stores `PENDING`, `APPROVED`, and `REJECTED` requests in
SQLite. Only pending requests can be approved/rejected normally. Product-video
artifact replacement can invalidate both pending and approved requests by exact,
recursive `artifact_id` match.

## Budgets

`BudgetEngine` and `BudgetRepository` in `hermes_personal/workflows/budgets.py` enforce total and per-channel limits with `reserve_budget`, `commit_budget`, and `release_budget` operations:

- **Durable Persistence**: Backed by the SQLite `budget_reservation` table. Active (`reserved`) and `committed` allocations count toward budget consumption; `released` allocations do not. State survives process restarts.
- **Atomic Reservation**: Uses `BEGIN IMMEDIATE` SQLite transactions to prevent race conditions across concurrent callers.
- **Idempotency**: `(owner_user_id, scope_id, idempotency_key)` combined with SHA-256 request digest deduplicates reservation retries without double deducting budget. Re-committing or re-releasing is idempotent. Key reuse with conflicting parameters raises `BudgetConflict`.
- **Isolation**: Owner and scope boundaries ensure distinct users/workflows operate under isolated budget pools.

## Background jobs

`JobDispatcher` runs daemon threads, supports bounded attempts, records results,
and exposes callbacks. Retries are immediate and process-local. A timed-out
helper thread cannot be killed safely, so a timeout does not prove the underlying
operation stopped.

## Recovery and Durable Outbox Delivery

`WorkflowRecoveryService` in `hermes_personal/workflows/recovery.py` implements durable outbox delivery guarantees for workflow notifications and side effects:

- **State Machine**: Outbox items progress through `pending` -> `leased` -> deleted (on successful acknowledgement) or `quarantined` (upon max attempt exhaustion).
- **Atomic Conditional Claim (`claim_outbox_batch`)**: Claims unclaimed or expired-lease outbox items using conditional SQL updates (`UPDATE workflow_outbox SET status = 'leased', worker_id = ?, lease_token = ?, leased_at = datetime('now'), lease_expires_at = datetime('now', '+30 seconds'), attempt_count = attempt_count + 1 WHERE outbox_id = ? AND (status = 'pending' OR (status = 'leased' AND lease_expires_at < datetime('now'))) AND (next_attempt_at IS NULL OR next_attempt_at <= datetime('now'))`).
- **Stale Lease ACK Rejection (`ack_outbox`)**: Deletes an outbox row only when given matching `outbox_id` and active `lease_token`. A stale ACK with an expired or mismatched lease token is rejected (`StaleLeaseError` / `LeaseExpired`), protecting against duplicate worker deletions.
- **Bounded Exponential Backoff**: Processing failures set `next_attempt_at` using bounded exponential backoff (`min(base_delay * 2^(attempt_count - 1), max_delay)`). Workers skip items before their scheduled retry timestamp.
- **Poison Message Quarantine & Requeue (`requeue_quarantined`)**: Messages exceeding max attempts (default 5) move to `quarantined` status to isolate poison messages. Operators can execute `requeue_quarantined(outbox_id)` to reset state to `pending`, clear `last_error`, and zero `attempt_count` for safe reprocessing.

## Product-video HITL

The canonical pipeline requires approval at Product Lock, Brief, Scene Plan,
Storyboard, and Final Video. Every job validates legal state, expected workflow
version, and input digest. Artifact replacement increments binding version,
clears descendants, and invalidates stale approvals.

## Verification

```powershell
uv run pytest tests/hermes_personal/workflows -q
uv run pytest tests/hermes_personal/product_video -q
uv run ruff check hermes_personal/workflows hermes_personal/product_video
```

Also test the canonical turn path when workflow events or operator commands are
changed, because cross-channel behavior is owned by `HermesTurnService`, not the
workflow module alone.
