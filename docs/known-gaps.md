# Hermes Personal Known Gaps

This is the source-audited quality-gate backlog. A design plan or passing unit
test does not close an item; the stated closure evidence is required.

| ID | Severity | Gap | Impact | Closure evidence |
| --- | --- | --- | --- | --- |
| HP-001 | Critical if exposed | Default `EventsAPI` auth accepts any non-empty token | Owner data can be exposed if default composition reaches an untrusted network | Owner-bound validator wiring plus negative auth tests and deployment config |
| HP-002 | High | Five child modules declared by `hermes start` are absent | Full runtime cannot launch from this checkout | Importable modules, real startup/readiness/shutdown smoke, no orphan process |
| HP-003 | High | `/api/turn` and `/api/omni/turn` are declared for cutover but not mounted | Web/Omni natural-language ingress is not production-wired | Authenticated routers call `HermesTurnService` with durable stores and E2E tests |
| HP-004 | High | `WorkflowEngine` commits before transition validation/application | Invalid command events may persist and recovered aggregate can be stale | Transition-before-commit implementation, atomic failure tests, restart recovery tests |
| HP-005 | High | `job_succeeded` target mapping conflicts with allowed-state table | Successful generic jobs cannot complete through the documented command | Correct terminal/next state contract and regression tests from dispatched/retried states |
| HP-006 | High for paid work | `BudgetEngine` is in-memory and only deduplicates commit, not reservation | Restart or duplicate reserve can permit inconsistent/duplicate cost authorization | Durable atomic reservation claim, owner/workflow scope, reconciliation tests |
| HP-007 | High for delivery | Outbox replay deletes rows before downstream acknowledgement | Delivery failure after replay read can lose pending notification intent | Ack/lease protocol or transactional consumer, retry count, poison-message policy |
| HP-008 | Medium | `JobDispatcher` timeout cannot stop the worker thread and retries have no backoff | Late side effects or duplicate expensive work after timeout | Cooperative cancellation/process isolation, reconciliation, bounded backoff tests |
| HP-009 | Medium | HTTP operator type and replay bounds are not runtime-validated | Unknown commands and abusive cursor/limit values can reach handlers | Pydantic/request validation, enum enforcement, bounds and negative tests |
| HP-010 | Medium | Default API event/artifact stores are in-memory and the durable adapter is not production-wired | Restart loses API projection data | EventRepository-compatible adapter and restart/replay test |
| HP-011 | Medium | No application rate limiting, request-size limit, or explicit CORS/trusted-proxy policy | Abuse and deployment ambiguity | Edge/application controls documented, configured, and tested |
| HP-012 | Medium | Startup callbacks are optional no-ops | `is_ready` can be true without migrations/discovery/recovery actually running | Production composition requires every callback and asserts step details |
| HP-013 | High | HTTP replay cursor uses per-turn `AgentEvent.sequence` as if owner-global | Events from later turns can be skipped or ambiguously ordered | Durable owner-global cursor/event offset and multi-turn replay/resume tests |
| HP-014 | High | Supervisor does not execute `ProcessSpec.readiness_probe` and marks a child healthy immediately after spawn | Runtime can report healthy before a service binds or becomes ready | Probe executor, startup gating on required probes, failure/restart tests |
| HP-015 | Medium | Child stdout/stderr are piped but not drained | Verbose child can block when OS pipe buffers fill | Log-drain/forwarding implementation and sustained-output smoke test |

## Triage order

1. Close HP-001 before any network exposure.
2. Close HP-002, HP-003, HP-010, HP-012, HP-013, and HP-014 before all-channel cutover.
3. Close HP-004 and HP-005 before relying on generic workflow recovery.
4. Close HP-006 through HP-008 before live paid-provider work.
5. Close HP-009, HP-011, and HP-015 as part of the production HTTP boundary.

## Maintenance rule

Update this file in the same change that closes or materially changes a gap.
Link the commit, tests, and operational evidence in the change report. Do not
delete history solely because a plan marks a gate complete.
