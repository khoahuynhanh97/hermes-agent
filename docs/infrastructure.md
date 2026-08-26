# Hermes Personal Infrastructure

## Implemented topology

The current bounded context is local-first. Its implemented infrastructure is:

| Layer | Current implementation | Durability |
| --- | --- | --- |
| Relational state | Python `sqlite3` with foreign keys enabled | Durable when backed by a persistent path |
| Turn events | `turn_execution`, `turn_event`, and `owner_event_cursor` tables | Durable, owner-global replay |
| Workflow state | workflow aggregate, events, processed commands, outbox | Durable |
| Capability catalog | immutable snapshots plus singleton active pointer | Durable |
| Learning | candidate, evidence, evaluation, version, event tables | Durable |
| Artifacts and skills | Local filesystem references | Depends on configured filesystem |
| Background work | Daemon threads through `JobDispatcher` | Process-local execution; no overlapping timeout retry |
| Process management | `subprocess.Popen(shell=False)` through `Supervisor` | Process lifecycle only |
| Gateway HTTP | FastAPI plus `HermesTurnService` | Durable SQLite composition |
| Public App API | FastAPI loopback reverse proxy | Stateless; browser-session boundary |
| Web frontend | React, TypeScript, Vite | Built static bundle |

There is no RabbitMQ, Kafka, Redis, distributed worker pool, or dead-letter
queue in the current source. `workflow_outbox` is a SQLite recovery mechanism;
it is not a broker queue or DLQ.

## SQLite layout

`hermes_personal/storage/sqlite.py` owns the schema and migration entry point.
The main table groups are:

- identity and sessions: `global_user_identity`, `channel_identity`,
  `conversation_session`, `workflow_handoff`;
- turns: `turn_execution`, `turn_event`, `legacy_session_cutover`;
- capabilities: `capability_snapshot`, `capability_snapshot_binding`,
  `capability_catalog_state`;
- workflows: `workflow`, `workflow_event`, `processed_command`,
  `workflow_outbox`, `budget_reservation`;
- learning: `task_outcome`, `learning_candidate`, `evidence_ref`,
  `learning_version`, `candidate_evaluation`, `learning_event`;
- approvals: `approval_request`, created by `ApprovalService`.

SQLite connections use `check_same_thread=False`, row dictionaries, and
`PRAGMA foreign_keys = ON`. Deployments must place the database on durable local
storage, back it up consistently, and avoid unsupported multi-host sharing.

## Declared process topology

`build_process_topology()` declares this ordered process set:

| Process | Declared module/command | Required |
| --- | --- | --- |
| gateway | `python -m hermes_personal.runtime.gateway_server` | yes |
| app API | `python -m hermes_personal.api.server` | yes |
| MCP discovery | `python -m hermes_personal.capabilities.mcp_runner` | configurable, yes |
| durable worker | `python -m hermes_personal.workflows.worker` | configurable, yes |
| Telegram | `python -m hermes_personal.gateway.platforms.telegram_runner` | configurable, no |
| Web dev server | `npm run dev -- --port <port>` in `web/` | development only, no |

The supervisor starts in declaration order, stops in reverse order, passes argv
without a shell, and uses bounded exponential restart policies. It waits for
HTTP/TCP/file readiness until the probe deadline and treats a required probe or
restart exhaustion as fatal. Child output is inherited instead of captured in
an unread pipe. Only platform essentials and each process's declared `env_keys`
are passed to children.

## Runtime configuration

`RuntimeConfig` defaults:

| Setting | Default |
| --- | --- |
| mode | `development` |
| gateway port | `8642` |
| application API port | `8000` |
| Web port | `3000` |
| Telegram/Web/workers/MCP | enabled |
| required secret names | `HERMES_TELEGRAM_TOKEN`, `HERMES_API_KEY` |

Production Web mode requires both `web_static_dir` and
`web_static_digest`. Ports must be unique. Secret validation checks presence and
reports names only, never values. The local runnable profile in
`runtime-config.local.yaml.example` disables Telegram, workers, and MCP, uses a
fake provider, and starts the Gateway, App API, and Web UI.

## Readiness contract

Liveness means the API process responds and its readiness probe does not mark it
dead. Readiness requires the startup report and all required component health
checks to pass. A running PID is insufficient.

`handle_start` runs `StartupCoordinator` before child processes start, then the
supervisor gates each enabled child on its `ProbeSpec`. Gateway and App API
health are HTTP-probed; the development Web server is also HTTP-probed. Custom
production startup callbacks remain the deployment's responsibility.

The HTTP health endpoints are documented in
[Integrations](integrations-spec.md#health-api).

## Background execution and recovery

`JobDispatcher` starts daemon threads. A timeout records a timeout result but
cannot forcibly terminate the underlying Python thread. Handlers must therefore
be bounded, cooperative, and safe if their result arrives after the caller has
timed out.

`WorkflowRecoveryService` lists persisted workflows and peeks SQLite outbox
messages without deleting them. `ack_outbox` deletes one stable record only
after confirmed delivery. This local outbox still has no lease, retry counter,
visibility timeout, or poison-message quarantine policy.

## Storage and backup guidance

- Keep the SQLite database and artifact root on persistent storage.
- Back up the database using SQLite-consistent backup tooling or while writers
  are stopped; do not copy a live database blindly.
- Treat artifact refs as immutable. Replace an artifact by creating a new ref and
  invalidating descendants rather than overwriting bytes in place.
- Do not place secrets in artifact metadata, workflow payloads, process argv, or
  logs.
- Test restore procedures with event replay and workflow version checks.

## Known runtime gaps

The core modules exist and pass real startup/readiness/turn/replay/shutdown
smoke coverage. These optional declared runners do not exist yet:

- `hermes_personal.capabilities.mcp_runner`
- `hermes_personal.workflows.worker`
- `hermes_personal.gateway.platforms.telegram_runner`

Use `runtime-config.local.yaml.example` to disable those services. Enabling one
of them is expected to fail its process start/readiness check rather than report
false health. `/api/turn` and `/api/omni/turn` are mounted on the canonical
Gateway and proxied by the App API.

Additional production gaps remain: `BudgetEngine` is process-local, outbox ACK
has no lease/quarantine protocol, application-level rate/body limits are not
implemented, and the production static digest is required by configuration but
is not yet checked by the App API process.

## Future distributed infrastructure

If throughput or host isolation requires a broker later, create an architecture
decision record before implementation. It must define message ownership,
delivery semantics, idempotency scope, retry budget, poison-message quarantine,
ordering, observability, and migration/rollback. Do not rename the existing
SQLite outbox as a DLQ.
