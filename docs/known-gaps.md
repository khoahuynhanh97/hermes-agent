# Hermes Personal Known Gaps

This is the source-audited quality-gate backlog. A design plan or passing unit
test does not close an item; the stated closure evidence is required.

| ID | Status | Severity | Gap | Impact | Closure evidence / Current status |
| --- | --- | --- | --- | --- | --- |
| HP-001 | MVP_DONE | Critical if exposed | Default `EventsAPI` auth accepts any non-empty token | Owner data can be exposed if default composition reaches an untrusted network | Closed: `EventsAPI` fails closed by default; Gateway wires `StaticBearerAuthenticator` with constant-time HMAC comparison. |
| HP-002 | MVP_DONE | High | Core child modules declared by `hermes start` | Full runtime cannot launch from checkout | Closed for local runtime: `gateway_server.py` and App API `server.py` implemented and verified. Optional runners (`mcp_runner`, `worker`, `telegram_runner`) are disabled by default in `runtime-config.local.yaml.example` and remain optional background topology. |
| HP-003 | MVP_DONE | High | `/api/turn` and `/api/omni/turn` mounted | Web/Omni natural-language ingress is not production-wired | Closed: Authenticated routers convert input to `AgentTurnRequest` and call `HermesTurnService` backed by SQLite `EventRepository`. |
| HP-004 | MVP_DONE | High | `WorkflowEngine` commits before transition validation/application | Invalid command events may persist and recovered aggregate can be stale | Closed: Transition validated and applied before event persistence; failure rollbacks tested. |
| HP-005 | MVP_DONE | High | `job_succeeded` target mapping conflicts with allowed-state table | Successful generic jobs cannot complete through the documented command | Closed: Correct terminal/next state contract and regression tests from dispatched/retried states verified. |
| HP-006 | MVP_DONE | High for paid work | `BudgetEngine` is in-memory and only deduplicates commit, not reservation | Restart or duplicate reserve can permit inconsistent/duplicate cost authorization | Closed: Durable SQLite-backed `budget_reservation` table, atomic `BEGIN IMMEDIATE` transactions, canonical capability policy integration (`CapabilityPolicyEvaluator`), true deterministic SHA-256 JSON request digest, policy audit snapshots (`policy_id`, `policy_version`), provider call count assertion (0 calls when budget fails), and 17 unit/concurrency + 4 capability integration tests passed. |
| HP-007 | MVP_DONE | High for delivery | Outbox replay deletes rows before downstream acknowledgement | Delivery failure after replay read can lose pending notification intent | Closed: Fully implemented durable outbox delivery safety boundaries with atomic SQLite claim (`pending` -> `leased` -> deleted/`quarantined`), worker lease tokens, lease expiration recovery, bounded exponential backoff (`next_attempt_at`), poison message quarantine (`quarantined`), and at-least-once delivery guarantees when a topic handler is registered. Safety mechanisms (bounded retries, ownership-safe ACK, transaction integrity) are verified for PERSONAL_HAPPY_PATH_V1. |
| HP-008 | MVP_DONE | Medium | Live provider adapters for ProductIntelligence/VideoFactory unconfigured | Production worker in `provider_mode="configured"` cannot execute live paid I/O | Closed for PERSONAL_HAPPY_PATH_V1: MCP adapters (`MCPProductIntelligenceAdapter`, `MCPVideoFactoryAdapter`) fully wired into `ProductVideoJobHandlers` and `OutboxDispatcher`. Includes structured payload decoding, immediate checkpointing of accepted `job_id` before polling, monotonic deadline enforcement, heartbeat lease renewal (`extend_lease`), structured terminal error propagation (`TerminalJobError` -> `quarantined`), and strict fail-closed configuration validation. Verified across 104 focused tests with deterministic MCP tools; live provider usage remains user opt-in via external MCP config in `~/.hermes/config.yaml`. |
| HP-009 | MVP_DONE | Medium | HTTP operator type and replay bounds not runtime-validated | Unknown commands and abusive cursor/limit values can reach handlers | Closed: `OperatorCommandType` runtime enum membership check including `"start_workflow"` and `"approve"`, and `after_seq >= 0`, `1 <= limit <= 500` bounds enforced. `POST /api/operator/command` routes `start_workflow` and `approve` (which advances workflow state and outbox queue). |
| HP-010 | MVP_DONE | Medium | Default API event/artifact stores in-memory | Restart loses API projection data | Closed: `EventRepository` durable SQLite store backs `/api/events/replay` with multi-turn history. |
| HP-011 | MVP_DONE | Medium | No application rate limiting, request-size limit, or explicit CORS/trusted-proxy policy | Abuse and deployment ambiguity | Closed: Implemented `RequestBodySizeLimitMiddleware` (enforces 10MB limit with HTTP 413), `TokenBucketRateLimiter` & `RateLimitMiddleware` (enforces configurable 120 req/min with HTTP 429 and `Retry-After`), and `CORSMiddleware` in `hermes_personal/application/middleware.py`; verified with unit/preflight tests. |
| HP-012 | MVP_DONE | Medium | Startup callbacks optional no-ops | `is_ready` can be true without migrations/discovery/recovery running | Closed: Wired strict mandatory callbacks into `StartupCoordinator` (`db_migration` runs `_migrate_schema`, `stale_lease_recovery` reclaims expired leases, `workflow_approval_recovery` verifies pending workflows, `capability_snapshot_activation` ensures default snapshot activation, and `dependency_probes` executes fast SQLite probe); verified with readiness lifecycle tests. |
| HP-013 | MVP_DONE | High | HTTP replay cursor uses per-turn sequence as owner-global | Events from later turns can be skipped or ambiguously ordered | Closed: Durable owner-global monotonic cursor allocated in `owner_event_cursor` table; tested across multi-turn and SQLite reopen. |
| HP-014 | MVP_DONE | High | Supervisor does not execute readiness probes | Runtime reports healthy before child binds | Closed: Supervisor executes HTTP/TCP/exec readiness probes before marking processes healthy. |
| HP-015 | MVP_DONE | Medium | Child stdout/stderr piped but not drained | Verbose child blocks when OS pipe buffers fill | Closed: Non-blocking log drain threads forward child outputs. |

## Status Definitions

- **MVP_DONE**: Closed with sufficient evidence for single-owner, single-machine, SQLite-backed Video Factory happy path.
- **HARDENING_DEFERRED**: Identified but deferred; not blocking MVP; requires explicit reopening for multi-worker scaling, HA, or multi-tenant production deployment.
- **PRODUCTION_HARDENED**: Fully closed for distributed, multi-tenant, high-availability production environments.

## Triage order

1. MVP_DONE items (HP-001 through HP-015) are fully closed with evidence for PERSONAL_HAPPY_PATH_V1.
2. Distributed/HA hardening (multi-worker pools, RabbitMQ/Kafka, HA replication) remains deferred for multi-node deployments.
3. Wire optional process runners (`mcp_runner`, `worker`, `telegram_runner`) when multi-process topology is deployed.

## Maintenance rule

Update this file in the same change that closes or materially changes a gap.
Link the commit, tests, and operational evidence in the change report. Do not
delete history solely because a plan marks a gate complete.
