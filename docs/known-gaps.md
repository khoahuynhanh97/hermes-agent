# Hermes Personal Known Gaps

This is the source-audited quality-gate backlog. A design plan or passing unit
test does not close an item; the stated closure evidence is required.

| ID | Status | Severity | Gap | Impact | Closure evidence / Current status |
| --- | --- | --- | --- | --- | --- |
| HP-001 | Closed | Critical if exposed | Default `EventsAPI` auth accepts any non-empty token | Owner data can be exposed if default composition reaches an untrusted network | Closed: `EventsAPI` fails closed by default; Gateway wires `StaticBearerAuthenticator` with constant-time HMAC comparison. |
| HP-002 | Partially Closed | High | Core child modules declared by `hermes start` | Full runtime cannot launch from checkout | Closed for local runtime: `gateway_server.py` and App API `server.py` implemented and verified. Optional runners (`mcp_runner`, `worker`, `telegram_runner`) are disabled by default in `runtime-config.local.yaml.example` and remain optional background topology. |
| HP-003 | Closed | High | `/api/turn` and `/api/omni/turn` mounted | Web/Omni natural-language ingress is not production-wired | Closed: Authenticated routers convert input to `AgentTurnRequest` and call `HermesTurnService` backed by SQLite `EventRepository`. |
| HP-004 | Closed | High | `WorkflowEngine` commits before transition validation/application | Invalid command events may persist and recovered aggregate can be stale | Closed: Transition validated and applied before event persistence; failure rollbacks tested. |
| HP-005 | Closed | High | `job_succeeded` target mapping conflicts with allowed-state table | Successful generic jobs cannot complete through the documented command | Closed: Correct terminal/next state contract and regression tests from dispatched/retried states verified. |
| HP-006 | Closed | High for paid work | `BudgetEngine` is in-memory and only deduplicates commit, not reservation | Restart or duplicate reserve can permit inconsistent/duplicate cost authorization | Closed: Durable SQLite-backed `budget_reservation` table, atomic `BEGIN IMMEDIATE` reservation transactions, SHA-256 request digest idempotency, owner/scope isolation, and 15/15 unit/concurrency tests passed. |
| HP-007 | Open | High for delivery | Outbox replay deletes rows before downstream acknowledgement | Delivery failure after replay read can lose pending notification intent | Closed against delete-before-ack (now deletes only after successful send). Full distributed lease/quarantine remains future enhancement. |
| HP-008 | Open | Medium | `JobDispatcher` timeout cannot stop worker thread and retries have no backoff | Late side effects or duplicate expensive work after timeout | Cooperative cancellation/process isolation, reconciliation, bounded backoff tests needed. |
| HP-009 | Closed | Medium | HTTP operator type and replay bounds not runtime-validated | Unknown commands and abusive cursor/limit values can reach handlers | Closed: `OperatorCommandType` runtime enum membership check and `after_seq >= 0`, `1 <= limit <= 500` bounds enforced. |
| HP-010 | Closed | Medium | Default API event/artifact stores in-memory | Restart loses API projection data | Closed: `EventRepository` durable SQLite store backs `/api/events/replay` with multi-turn history. |
| HP-011 | Open | Medium | No application rate limiting, request-size limit, or explicit CORS/trusted-proxy policy | Abuse and deployment ambiguity | Edge/application controls documented, configured, and tested. |
| HP-012 | Open | Medium | Startup callbacks optional no-ops | `is_ready` can be true without migrations/discovery/recovery running | Production composition requires all callbacks and step assertions. |
| HP-013 | Closed | High | HTTP replay cursor uses per-turn sequence as owner-global | Events from later turns can be skipped or ambiguously ordered | Closed: Durable owner-global monotonic cursor allocated in `owner_event_cursor` table; tested across multi-turn and SQLite reopen. |
| HP-014 | Closed | High | Supervisor does not execute readiness probes | Runtime reports healthy before child binds | Closed: Supervisor executes HTTP/TCP/exec readiness probes before marking processes healthy. |
| HP-015 | Closed | Medium | Child stdout/stderr piped but not drained | Verbose child blocks when OS pipe buffers fill | Closed: Non-blocking log drain threads forward child outputs. |

## Triage order

1. Close HP-006 through HP-008 before live paid-provider work.
2. Close HP-011 and HP-012 as part of the production edge and startup composition.
3. Wire optional process runners (`mcp_runner`, `worker`, `telegram_runner`) when multi-process topology is deployed.

## Maintenance rule

Update this file in the same change that closes or materially changes a gap.
Link the commit, tests, and operational evidence in the change report. Do not
delete history solely because a plan marks a gate complete.
