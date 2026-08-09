# P4A Canonical Durable Job Plane

## Decision

`hermes.jobs.JobRepository` is the canonical durable repository for newly
migrated workloads. It already owns the strongest repository semantics in this
codebase: owner-scoped persistence, idempotent enqueue, SQLite
`BEGIN IMMEDIATE` claims, bounded attempts, retry/DLQ visibility, cooperative
cancellation, and explicit recovery. A small schema extension adds worker
leases for bounded stale-job recovery.

`CanonicalJobRepository` adapts that contract to the existing application
`Job` port used by Video MCP. The older `SQLiteJobRepository` remains available
for compatibility with pre-P4A callers and tests; it is not the source of
truth for newly migrated durable workloads.

## State machine

Canonical states remain `queued`, `running`, `completed`, `failed`, and
`cancelled`; the Video/application adapter maps `completed` to the domain
status `succeeded`.

```text
queued -> running -> completed
                 -> failed
                 -> cancelled (cooperative request)
queued -> cancelled
running --expired lease--> queued
```

Retryable failure returns to `queued` until `attempts == max_attempts`, after
which the inspectable terminal state is `failed`. Running cancellation sets a
request flag; the worker acknowledges it at a safe boundary and does not claim
it again.

## Worker contract

`workers.job_worker.CanonicalJobWorker` claims a job, validates task type and
bounded payload paths, dispatches through an explicit registry, executes the
existing `DesktopRuntime` capability, persists a structured result, and marks
success or failure. It contains no LLM, semantic routing, skill selection,
scheduler, or HITL logic.

The first migrated handlers are deterministic `video.cut` and
`video.render`.

## Compatibility classifications

| Component | Classification |
| --- | --- |
| `hermes.jobs.JobRepository` | CANONICAL |
| `workers/job_worker.py` | CANONICAL |
| `CanonicalJobRepository` | CANONICAL adapter |
| `core/agent_jobs.py` | KEEP_TEMPORARY / compatibility required |
| `core/job_watcher.py` | STILL_REQUIRED for legacy learning workflows |
| `scripts/run_job_worker.py` | KEEP_TEMPORARY legacy entrypoint |
| `scripts/affiliate_research_worker.py` | MIGRATE_LATER; scheduler/affiliate scope excluded |
| `hermes/tools/auto_scheduler.py` | MIGRATE_LATER; P4B |
| `hermes/adapters/sqlite/job_repository.py` | KEEP_TEMPORARY compatibility implementation |
| `affiliate_worker.py` | MIGRATE_LATER / legacy affiliate path |

P4A does not delete or retire these implementations.
