# Hermes Personal Operations Runbook

This runbook covers the implemented operational surfaces and the checks required
before deployment. Read [Infrastructure](../infrastructure.md) for topology and
storage details and [Security](../security-and-auth.md) before exposing HTTP.

## Current operational status

The runtime configuration, startup coordinator, process topology, supervisor,
readiness model, FastAPI router factory, and tests exist. The complete
`hermes start` process set is not launchable from this checkout because five
declared child modules are absent. Do not use a successful topology/supervisor
unit test as production startup evidence.

Missing modules are listed in
[Infrastructure: Known runtime gaps](../infrastructure.md#known-runtime-gaps).

## Safe offline verification

These checks do not require a live or paid provider:

```powershell
uv run pytest tests/hermes_personal -q
uv run ruff check hermes_personal tests/hermes_personal
npm --prefix web run build
git diff --check
```

For focused runtime/API coverage:

```powershell
uv run pytest tests/hermes_personal/e2e -q
uv run pytest tests/hermes_personal/runtime -q
uv run pytest tests/hermes_personal/runtime/test_application_api.py -q
```

Use actual paths returned by `rg --files tests/hermes_personal` if a focused
directory has been renamed. Before an upstream PR, run `scripts/run_tests.sh`
from a supported shell for CI parity.

## FastAPI composition smoke

The application factory can be tested in process with a configured
`ReadinessProbe`, owner-bound `auth_validator`, durable event-store adapter,
artifact store, and command handler. The default composition is local/test only:

- no readiness probe means `/health/ready` returns 503;
- default auth accepts any non-empty token;
- default event store is process-local memory;
- missing command handler returns `accepted` without durable processing.

Do not expose that default composition to an untrusted network.

Implemented routes:

```text
GET  /health/live
GET  /health/ready
GET  /health/components/{name}
GET  /api/events
GET  /api/events/replay
POST /api/operator/command
GET  /api/artifacts/{artifact_id}
```

`/api/turn` and `/api/omni/turn` are not currently mounted.

## Startup gate

Production composition must inject real callbacks for every mandatory startup
step:

1. config validation and required-secret presence;
2. SQLite migration;
3. expired lease recovery;
4. workflow/outbox recovery while preserving pending approvals;
5. MCP discovery;
6. capability snapshot activation;
7. mandatory dependency probes;
8. ingress readiness.

A missing callback is currently a completed no-op. Verify step details, not only
the final `is_ready` flag.

## Supervisor behavior

The supervisor starts children in declared order and stops them in reverse.
`SIGINT`/`SIGTERM` requests graceful shutdown. Each child gets its configured
timeout, then is killed if still alive. Required restart exhaustion returns
non-zero and triggers shutdown; optional exhaustion reports degraded.

Current gaps: child readiness probes are declared but not executed; status is set
to healthy immediately after process creation. Captured stdout/stderr are not
drained. These must be fixed before treating supervisor health as readiness.

Before enabling the launcher, perform a real smoke test that verifies:

- every module imports and binds its configured port;
- readiness reflects dependency state, not PID existence;
- no secret appears in argv or logs;
- repeated child crashes respect attempt windows/backoff;
- Ctrl+C leaves no child process;
- SQLite remains readable and workflow/event replay succeeds after restart.

## Database and recovery

- Use a persistent SQLite path with restricted ACLs.
- Apply migrations before ingress becomes ready.
- Back up using a SQLite-consistent mechanism.
- Test restore with owner-scoped event replay and workflow version reads.
- Treat `workflow_outbox` as an outbox, not a broker or DLQ.
- Reconcile delivery before deleting/replaying failed external work.

## Incident triage

| Symptom | First checks | Safe action |
| --- | --- | --- |
| readiness 503 | failure code, startup step details, required components | Repair dependency and rerun startup |
| duplicate turn in progress | canonical turn ID and last committed event | Wait/replay; do not create a new paid action |
| idempotency conflict | owner, key, semantic request digest | Correct request or use a new logical key |
| workflow version conflict | persisted aggregate/version and command ID | Reload, reconcile, retry intentionally |
| HITL blocked | current state and approval record | Obtain explicit approval; never bypass |
| digest mismatch | input ref/version/digest and binding chain | Replace stale input and invalidate descendants |
| child restart exhausted | stderr, exit code, restart history | Keep required ingress down; fix root cause |
| SSE appears idle | replay cursor, owner auth, committed event store | Inspect by turn; current cursor is not owner-global and must not drive production resume |

## Packaging

Normal upstream distribution uses the supported installer, Docker, or Nix. For
development:

```powershell
uv sync
```

Wheel verification is permitted only through the repository's Nix/CI override:

```powershell
$env:HERMES_NIX_BUILD = "1"
uv build --wheel
```

Delete local `build/`, `dist/`, and generated metadata after acceptance if they
are not intended artifacts; never delete unrelated user files.

## Acceptance evidence

An operations completion report must include exact commands, pass counts, commit
or diff range, remaining uncommitted files, runtime gaps, and confirmation that
no paid provider was called. UI acceptance requires real browser evidence when
the criterion explicitly asks for desktop/mobile rendering; build/API tests are
not equivalent unless the acceptance plan is formally adjusted.
