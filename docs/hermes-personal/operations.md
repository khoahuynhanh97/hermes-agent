# Hermes Personal Operations Runbook

This runbook covers the implemented operational surfaces and the checks required
before deployment. Read [Infrastructure](../infrastructure.md) for topology and
storage details and [Security](../security-and-auth.md) before exposing HTTP.

## Supported local runtime

The core `hermes start` process set is launchable from this checkout: canonical
Gateway, public App API, durable SQLite replay, and the development Web UI. The
standalone MCP discovery, durable-worker, and Telegram runner modules are not
packaged yet. The checked-in local profile disables them rather than simulating
success.

Start the deterministic no-cost profile from PowerShell:

```powershell
uv sync --extra web --extra dev
npm --prefix web install
$env:HERMES_HOME = Join-Path $PWD ".runtime\hermes"
$env:HERMES_API_KEY = [Convert]::ToHexString(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLowerInvariant()
$env:HERMES_OWNER_ID = "local-owner"
uv run hermes start --config .\runtime-config.local.yaml.example --no-open-browser
```

Open `http://127.0.0.1:3000/omni`. The fake provider emits deterministic
`AgentEvent` records and does not call a paid provider. State is persisted at
`$env:HERMES_HOME\hermes.db`. Stop with `Ctrl+C`.

To use the configured upstream agent, complete `uv run hermes setup`, copy the
example profile, and set `runtime.provider_mode: configured`. That mode can run
tools and incur provider cost; it is not used for automated acceptance.

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

## HTTP composition

The Gateway composes `HermesTurnService` with SQLite identity, session, turn,
event, and owner-global cursor stores. The App API is a thin reverse proxy; it
does not construct a second agent runtime. It injects a random browser session
token and keeps `HERMES_API_KEY` server-side for loopback requests.

The generic `create_application()` factory remains suitable for tests and
custom composition only: without injected readiness, auth, durable stores, and
handlers it fails closed or reports unavailable. Do not expose an unconfigured
factory to an untrusted network.

Implemented routes:

```text
GET  /health/live
GET  /health/ready
GET  /health/components/{name}
GET  /api/events
GET  /api/events/replay
POST /api/operator/command
GET  /api/artifacts/{artifact_id}
POST /api/turn
POST /api/omni/turn
```

## Startup gate

Production composition must supply real callbacks for every mandatory startup
step; the local profile performs the implemented config, database, recovery,
and process-readiness path:

1. config validation and required-secret presence;
2. SQLite migration;
3. expired lease recovery;
4. workflow/outbox recovery while preserving pending approvals;
5. MCP discovery;
6. capability snapshot activation;
7. mandatory dependency probes;
8. ingress readiness.

A missing custom callback remains a completed no-op. Verify step details, not
only the final `is_ready` flag, before production exposure.

## Worker producer/consumer wiring

The product-to-video pipeline ties `job.dispatch` to handlers via `worker.py`:
- **Producer**: `start_product_video_workflow()` via `/api/operator/command` registers `dispatch` jobs.
- **Consumer**: `create_product_video_topic_handlers()` in `handlers.py` registers handlers (`research`, `resource_pack`, `lock`, `creative_brief`, `scene_plan`, `storyboard`, `render`, `export`). `durable_worker` composes `create_product_video_topic_handlers()` with `OutboxDispatcher`. This wiring verified with 11 tests in `tests/hermes_personal/workflows/test_product_video_outbox.py`.

Example worker launch:
```powershell
$env:HERMES_PROVIDER_MODE = "fake"
uv run python -m hermes_personal.workflows.worker --db-path ~/.hermes/hermes.db --poll-interval 1.0
```

## Supervisor behavior

The supervisor starts children in declared order and stops them in reverse.
`SIGINT`/`SIGTERM` requests graceful shutdown. Each child gets its configured
timeout, then is killed and reaped if still alive. HTTP/TCP/file readiness probes
retry until their deadline; required probe or restart exhaustion returns
non-zero. Child stdout/stderr are inherited, so verbose services cannot fill an
unread pipe. Child environments contain only platform essentials and the keys
declared by each `ProcessSpec`.

Before enabling the launcher, perform a real smoke test that verifies:

- every enabled module imports and binds its configured port;
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
- Replay only peeks. Delete a row through `ack_outbox` after confirmed delivery.
- `BudgetEngine` is SQLite-backed via `budget_reservation` table (HP-006). Do not authorize paid work unless budget reservations are committed atomically in a transaction.
- Timed-out Python job threads cannot be forcibly killed. Automatic overlap is
  blocked, but handlers still require reconciliation.

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
| SSE appears idle | replay cursor, owner auth, committed event store | Replay from `next_cursor`; the cursor is durable and owner-global |

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
