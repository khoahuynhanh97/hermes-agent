# Hermes Personal Workflow System Architecture

## Overview
The Hermes Personal Workflow Engine provides durable, state-machine driven, multi-stage workflow execution across all natural-language ingress channels (Telegram, CLI, Web, Omni).

## Key Components

### 1. Workflow Models & Definitions (`hermes_personal/workflows/models.py`, `definitions.py`)
- Defines `WorkflowState`, `WorkflowEvent`, `WorkflowDefinition`, and `WorkflowInstance`.
- Pre-packaged canonical workflow definitions:
  - `product_to_video`: Multi-stage video creation pipeline with mandatory artifact gates (`creative_brief`, `scene_plan`, `final_video`).
  - `knowledge_learning`: Governed KB lesson extraction and human-in-the-loop review.

### 2. Workflow Persistence & Idempotency (`hermes_personal/workflows/repository.py`, `sqlite.py`)
- Backed by SQLite tables: `workflow`, `workflow_event`, `processed_command`, `workflow_outbox`.
- Enforces strict atomic transactions with version optimistic locking.
- Idempotent command processing: duplicate command IDs return cached results without re-emitting events.

### 3. Workflow Engine (`hermes_personal/workflows/engine.py`)
- State machine transition validation (`initial` -> `started` -> `approval_requested` -> `approved` -> `job_dispatched` -> `job_succeeded` / `job_failed` -> ...).
- Validates required artifact slots before state transitions.

### 4. Cross-Channel Shared Business Approvals (`hermes_personal/workflows/approvals.py`)
- SQLite-backed `ApprovalService` managing `submit_request`, `approve`, `reject`, and pending state transition rules across ingress channels.

### 5. Cross-Channel Shared Budget Engine (`hermes_personal/workflows/budgets.py`)
- `BudgetEngine` with `BudgetPolicy` enforcing multi-channel limit constraints, allocation reservations, atomic commits, and releases.

### 6. Async Background Job Dispatcher (`hermes_personal/workflows/jobs.py`)
- `JobDispatcher` managing background worker threads, success/failure callback routing, retry policies, and timeout guards.

### 7. Restart Recovery & Outbox Replay (`hermes_personal/workflows/recovery.py`)
- `WorkflowRecoveryService` providing crash restart state reconstruction (`recover_pending_workflows`) and pending outbox replay (`replay_outbox`).

## Operator Verification
Run the complete workflow test suite:
```bash
uv run pytest tests/hermes_personal/workflows -q
```
