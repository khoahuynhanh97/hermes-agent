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
| HP-008 | MVP_OPEN | Medium | `JobDispatcher` timeout cannot stop worker thread and retries have no backoff | Late side effects or duplicate expensive work after timeout | Partial: single-machine Video Factory happy-path delivery is proven in `tests/hermes_personal/workflows/test_product_video_outbox.py`; remaining gap is runtime composition wiring of `product_video` topic handler into `durable_worker` and explicit timeout/backoff hardening. |
| HP-009 | MVP_DONE | Medium | HTTP operator type and replay bounds not runtime-validated | Unknown commands and abusive cursor/limit values can reach handlers | Closed: `OperatorCommandType` runtime enum membership check and `after_seq >= 0`, `1 <= limit <= 500` bounds enforced. |
| HP-010 | MVP_DONE | Medium | Default API event/artifact stores in-memory | Restart loses API projection data | Closed: `EventRepository` durable SQLite store backs `/api/events/replay` with multi-turn history. |
| HP-011 | HARDENING_DEFERRED | Medium | No application rate limiting, request-size limit, or explicit CORS/trusted-proxy policy | Abuse and deployment ambiguity | Edge/application controls documented, configured, and tested. |
| HP-012 | HARDENING_DEFERRED | Medium | Startup callbacks optional no-ops | `is_ready` can be true without migrations/discovery/recovery running | Production composition requires all callbacks and step assertions. |
| HP-013 | MVP_DONE | High | HTTP replay cursor uses per-turn sequence as owner-global | Events from later turns can be skipped or ambiguously ordered | Closed: Durable owner-global monotonic cursor allocated in `owner_event_cursor` table; tested across multi-turn and SQLite reopen. |
| HP-014 | MVP_DONE | High | Supervisor does not execute readiness probes | Runtime reports healthy before child binds | Closed: Supervisor executes HTTP/TCP/exec readiness probes before marking processes healthy. |
| HP-015 | MVP_DONE | Medium | Child stdout/stderr piped but not drained | Verbose child blocks when OS pipe buffers fill | Closed: Non-blocking log drain threads forward child outputs. |

## Status Definitions

- **MVP_DONE**: Closed with sufficient evidence for single-owner, single-machine, SQLite-backed Video Factory happy path.
- **HARDENING_DEFERRED**: Identified but deferred; not blocking MVP; requires explicit reopening for multi-worker scaling, HA, or multi-tenant production deployment.
- **PRODUCTION_HARDENED**: Fully closed for distributed, multi-tenant, high-availability production environments.

## Triage order

1. MVP_DONE items (HP-001 through HP-007, HP-009, HP-010, HP-013 through HP-015) are sufficient for PERSONAL_HAPPY_PATH_V1.
2. HARDENING_DEFERRED items (HP-008, HP-011, HP-012) require explicit authorization and reopening before distributed/HA work begins.
3. Wire optional process runners (`mcp_runner`, `worker`, `telegram_runner`) when multi-process topology is deployed.

## Maintenance rule

Update this file in the same change that closes or materially changes a gap.
Link the commit, tests, and operational evidence in the change report. Do not
delete history solely because a plan marks a gate complete.
