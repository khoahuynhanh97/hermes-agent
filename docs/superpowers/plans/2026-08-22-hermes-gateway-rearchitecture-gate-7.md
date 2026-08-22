# Hermes One Command Runtime Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver `hermes start` as the single operator command for a ready, observable, restart-safe Hermes runtime and cut all four production channels over without semantic bypasses or fake UI state.

**Architecture:** A project plugin registers the upstream `hermes start` CLI command. A supervisor starts independent process specs, performs migrations/recovery/discovery/readiness in order, restarts failed children with bounded backoff, and exposes one health model. Cutover uses shadow parity and reversible channel flags before legacy paths are retired.

**Tech Stack:** Python 3.10+, upstream `PluginContext.register_cli_command`, subprocess/asyncio, FastAPI health endpoints, structured JSON logs, SQLite events, pytest fakes, Playwright for Web acceptance, `uv`.

## Global Constraints

- Gates 1-6 must pass before final production cutover.
- The operator command is exactly `hermes start`.
- `hermes start` always makes the Web surface available.
- Ingress becomes ready only after required configuration, migrations, workflow recovery, MCP discovery/snapshot, and mandatory dependency health pass.
- Child restart never changes or loses durable workflow state.
- Web and Telegram render real `AgentEvent`/workflow state; simulated progress and fake asset IDs are prohibited.
- Secrets and raw sensitive payloads are redacted from logs/events/health responses.
- Legacy removal occurs only after parity, reconciliation, rollback, and observation criteria pass.
- Tests use fake processes/providers and no live paid calls.

---

## File Map

- `hermes_personal/observability/context.py`: correlation context propagation.
- `hermes_personal/observability/redaction.py`: structured secret/sensitive-data redaction.
- `hermes_personal/observability/health.py`: process/dependency/readiness model.
- `hermes_personal/runtime/processes.py`: immutable process specifications.
- `hermes_personal/runtime/supervisor.py`: lifecycle, signals, restart, and shutdown.
- `hermes_personal/runtime/startup.py`: validation/migration/recovery/discovery/readiness sequence.
- `hermes_personal/runtime/cli.py`: `start` parser and handler.
- `hermes_personal/runtime/plugin.py`: CLI registration through `PluginContext`.
- `web/src/hooks/useHermesEventStream.ts`: cursor-based durable Agent Event stream.
- `web/src/hooks/useHermesOperator.ts`: authenticated deterministic command client.
- `web/src/types/hermes.ts`: Web contract projection for events, workflow, approval, and artifacts.
- `web/src/pages/ChatPage.tsx`: canonical Web Chat using the Hermes event stream.
- `web/src/pages/OmniChatPage.tsx`: Omni presentation over the same Agent Turn/event APIs.
- `hermes_personal/cutover/inventory.py`: natural-language and deterministic path inventory.
- `hermes_personal/cutover/parity.py`: shadow comparison and release decision.
- `hermes_personal/cutover/retirement.py`: guarded legacy retirement checks.

### Task 1: Standardize Correlation, Redaction, And Health Records

**Files:**
- Create: `hermes_personal/observability/context.py`
- Create: `hermes_personal/observability/redaction.py`
- Create: `hermes_personal/observability/health.py`
- Create: `hermes_personal/observability/__init__.py`
- Test: `tests/hermes_personal/runtime/test_observability.py`

**Interfaces:**
- Consumes: principal/session/turn/workflow/job/approval/tool IDs and structured fields.
- Produces: redacted structured records and aggregate readiness.

- [ ] **Step 1: Write correlation and redaction tests**

```python
def test_correlation_chain_is_preserved():
    context = CorrelationContext("user:1", "session:1", "turn:1", "wf:1", "job:1", "approval:1", "tool:1")
    assert context.as_log_fields()["workflow_id"] == "wf:1"

@pytest.mark.parametrize("key", ["authorization", "api_key", "token", "cookie", "password"])
def test_secret_fields_are_redacted(key):
    assert redact({key: "secret", "workflow_id": "wf:1"}) == {key: "[REDACTED]", "workflow_id": "wf:1"}

def test_required_unhealthy_dependency_blocks_readiness():
    report = HealthReport.from_components((component("gateway", True, "healthy"), component("mcp", True, "unavailable")))
    assert report.ready is False
```

- [ ] **Step 2: Verify red and implement immutable models**

Run: `uv run pytest tests/hermes_personal/runtime/test_observability.py -q`

Expected: FAIL on missing package.

Use status values `starting`, `healthy`, `degraded`, `unavailable`, `stopping`, `stopped`. Readiness is true only when every required component is healthy; optional degraded components affect liveness detail but not readiness. Redact recursively by normalized key and configured value fingerprints before serialization.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/runtime/test_observability.py -q`

Expected: all tests pass.

```powershell
git add -- hermes_personal/observability tests/hermes_personal/runtime/test_observability.py
git commit -m "feat: add runtime observability contracts"
```

### Task 2: Define Runtime Process Topology And Environment Contract

**Files:**
- Create: `hermes_personal/runtime/processes.py`
- Create: `hermes_personal/runtime/config.py`
- Create: `hermes_personal/runtime/__init__.py`
- Test: `tests/hermes_personal/runtime/test_processes.py`

**Interfaces:**
- Consumes: validated runtime mode, ports, executable paths, and non-secret configuration.
- Produces: ordered immutable `ProcessSpec` records.

- [ ] **Step 1: Write topology tests**

Assert specs exist for Gateway/Agent Runtime, Application API, Telegram adapter, durable workers, MCP health/discovery, and Web UI. Development Web uses a frontend child process; production Web is served by Application API from a verified static bundle. Assert no command line contains secret values.

- [ ] **Step 2: Verify red and implement specs**

Run: `uv run pytest tests/hermes_personal/runtime/test_processes.py -q`

Expected: FAIL on missing runtime package.

```python
@dataclass(frozen=True)
class ProcessSpec:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    env_keys: tuple[str, ...]
    required: bool
    readiness_probe: ProbeSpec
    shutdown_timeout_seconds: float
    restart: RestartPolicy

@dataclass(frozen=True)
class RestartPolicy:
    max_attempts: int
    window_seconds: float
    base_backoff_seconds: float
    max_backoff_seconds: float
```

Build argv lists without shell interpolation. Validate unique names/ports, existing executable/cwd, production static manifest digest, and required secret presence without logging values.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/runtime/test_processes.py -q`

Expected: all topology tests pass.

```powershell
git add -- hermes_personal/runtime tests/hermes_personal/runtime/test_processes.py
git commit -m "feat: define hermes runtime topology"
```

### Task 3: Implement Supervisor Lifecycle And Bounded Restart

**Files:**
- Create: `hermes_personal/runtime/supervisor.py`
- Test: `tests/hermes_personal/runtime/test_supervisor.py`

**Interfaces:**
- Consumes: process specs, injected process runner, clock, and health sink.
- Produces: `Supervisor.run()`, graceful shutdown, restart events, and terminal exit code.

- [ ] **Step 1: Write fake-process lifecycle tests**

Test ordered start, unexpected child exit, exponential bounded restart, attempt-window reset, required child exhausted causing nonzero supervisor exit, optional child degraded without global shutdown, SIGINT/CTRL_BREAK graceful reverse-order stop, forced kill after timeout, and no orphan children.

- [ ] **Step 2: Verify red and implement without shell mode**

Run: `uv run pytest tests/hermes_personal/runtime/test_supervisor.py -q`

Expected: FAIL on missing supervisor.

Use an injected `ProcessRunner.start(spec) -> ChildProcess` with argv sequence, `shell=False`, process-group isolation, stdout/stderr line readers, and redaction before logging. Backoff is `min(base * 2 ** attempt, max)` plus an injected deterministic jitter source. Shutdown stops ingress first, drains workers, then stops dependencies in reverse start order.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/runtime/test_supervisor.py -q`

Expected: all lifecycle tests pass.

```powershell
git add -- hermes_personal/runtime/supervisor.py tests/hermes_personal/runtime/test_supervisor.py
git commit -m "feat: supervise hermes runtime processes"
```

### Task 4: Gate Ingress On Startup Recovery And Readiness

**Files:**
- Create: `hermes_personal/runtime/startup.py`
- Create: `hermes_personal/runtime/readiness.py`
- Test: `tests/hermes_personal/runtime/test_startup.py`

**Interfaces:**
- Consumes: config validator, migration runner, workflow/job recovery, capability reload, dependency probes.
- Produces: `StartupCoordinator.prepare() -> StartupReport` and readiness state.

- [ ] **Step 1: Write exact startup order and failure tests**

Assert order: config validation, DB migration, stale lease recovery, waiting workflow/approval recovery, MCP discovery, capability snapshot activation, mandatory dependency probes, then ingress ready. Any failed mandatory step stops before ready and reports a machine-readable failure code. A rerun after partial success is idempotent.

- [ ] **Step 2: Verify red and implement coordinator**

Run: `uv run pytest tests/hermes_personal/runtime/test_startup.py -q`

Expected: FAIL on missing coordinator.

Record each step start/end/status/latency in `StartupReport`. Never mark ready from process existence alone. Recovery requeues only expired leases, leaves pending approvals intact, and resumes outbox delivery from persisted offsets.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/runtime/test_startup.py -q`

Expected: all order/recovery tests pass.

```powershell
git add -- hermes_personal/runtime/startup.py hermes_personal/runtime/readiness.py tests/hermes_personal/runtime/test_startup.py
git commit -m "feat: gate ingress on runtime readiness"
```

### Task 5: Register The Exact `hermes start` Command

**Files:**
- Create: `hermes_personal/runtime/cli.py`
- Create: `hermes_personal/runtime/plugin.py`
- Modify: `plugins/hermes_personal/__init__.py`
- Modify: `plugins/hermes_personal/plugin.yaml`
- Test: `tests/hermes_personal/runtime/test_cli.py`

**Interfaces:**
- Consumes: upstream `PluginContext.register_cli_command(name, help, setup_fn, handler_fn, description)`.
- Produces: `hermes start [--mode development|production] [--config PATH]`.

- [ ] **Step 1: Write CLI registration and exit-code tests**

Test that plugin discovery adds exactly one `start` command, default mode comes from validated config, explicit mode/config flags parse, readiness summary prints no secrets, CTRL-C returns zero after clean shutdown, and startup failure returns nonzero with failing component/code.

- [ ] **Step 2: Verify red and register through the public plugin API**

Run: `uv run pytest tests/hermes_personal/runtime/test_cli.py -q`

Expected: FAIL because `start` is absent.

```python
def register(ctx: PluginContext) -> None:
    ctx.register_cli_command(
        name="start",
        help="Start the complete Hermes personal runtime",
        description="Validate, recover, start, and supervise every Hermes service.",
        setup_fn=setup_start_parser,
        handler_fn=handle_start,
    )
```

`setup_start_parser` adds only `--mode`, `--config`, and `--no-open-browser`; `handle_start` builds validated specs, runs startup, then supervisor. Do not add a second console script and do not patch `hermes_cli.main:main` unless the public plugin registration contract test proves upstream cannot discover installed project plugins.

- [ ] **Step 3: Verify installed CLI and commit**

```powershell
uv run pytest tests/hermes_personal/runtime/test_cli.py -q
uv run hermes start --help
```

Expected: tests pass; help lists the three flags and exits `0` without starting processes.

```powershell
git add -- hermes_personal/runtime/cli.py hermes_personal/runtime/plugin.py tests/hermes_personal/runtime/test_cli.py
git commit -m "feat: add one command hermes runtime startup"
```

### Task 6: Serve Real Events And Real Web Artifacts

**Files:**
- Create: `hermes_personal/application/health_api.py`
- Create: `hermes_personal/application/events_api.py`
- Create: `web/src/hooks/useHermesEventStream.ts`
- Create: `web/src/hooks/useHermesOperator.ts`
- Create: `web/src/types/hermes.ts`
- Modify: `web/src/pages/ChatPage.tsx`
- Create: `web/src/pages/OmniChatPage.tsx`
- Modify: `web/src/App.tsx`
- Test: `tests/hermes_personal/runtime/test_application_api.py`
- Test: `tests/hermes_personal/runtime/test_no_fake_progress.py`

**Interfaces:**
- Consumes: health report, durable Agent Events, workflow/artifact projections.
- Produces: authenticated health/readiness, event stream, operator command, and artifact metadata endpoints.

- [ ] **Step 1: Write API contract tests**

Test `/health/live`, `/health/ready`, owner-filtered event resume from sequence, reconnect replay, authenticated operator command submission, artifact metadata from canonical refs, and 404/403 behavior. Static scan must reject timers that synthesize progress, `mock/fake/demo` artifact IDs in production adapters, and direct provider calls from Web/Omni.

- [ ] **Step 2: Verify red and implement projections only**

Run: `uv run pytest tests/hermes_personal/runtime/test_application_api.py tests/hermes_personal/runtime/test_no_fake_progress.py -q`

Expected: FAIL until endpoints/adapters are implemented.

Events API reads committed events by owner and monotonic sequence, sends heartbeat separately from progress, and resumes from client cursor. Artifact API returns owner/type/version/digest plus a time-limited delivery reference from the owning context; it never invents media URLs.

- [ ] **Step 3: Verify and commit**

Run the same command; expected all API and static checks pass.

```powershell
git add -- hermes_personal/application/health_api.py hermes_personal/application/events_api.py web/src/hooks/useHermesEventStream.ts web/src/hooks/useHermesOperator.ts web/src/types/hermes.ts web/src/pages/ChatPage.tsx web/src/pages/OmniChatPage.tsx web/src/App.tsx tests/hermes_personal/runtime/test_application_api.py tests/hermes_personal/runtime/test_no_fake_progress.py
git commit -m "feat: expose real runtime events and health"
```

### Task 7: Cut Over Four Channels With Shadow Parity And Guarded Retirement

**Files:**
- Create: `hermes_personal/cutover/inventory.py`
- Create: `hermes_personal/cutover/parity.py`
- Create: `hermes_personal/cutover/retirement.py`
- Create: `hermes_personal/cutover/__init__.py`
- Test: `tests/hermes_personal/cutover/test_parity.py`
- Test: `tests/hermes_personal/cutover/test_retirement.py`
- Create: `docs/hermes-personal/cutover-runbook.md`

**Interfaces:**
- Consumes: path inventory, shadow results, migration reconciliation, rollback config, and observation metrics.
- Produces: reversible channel cutover decisions and retirement authorization.

- [ ] **Step 1: Inventory every production entry path**

Classify each Telegram/CLI/Web/Omni route as natural language, operator command, health/static, or prohibited direct provider path. The inventory test fails when a route is unclassified or when natural language does not terminate at `HermesTurnService`.

- [ ] **Step 2: Implement semantic parity comparison**

Compare outcome category, clarification requirement, selected stable capability IDs, workflow type/state, approval gates, artifact ownership/version/digest, terminal status, and bounded latency/cost deltas. Do not compare prose byte-for-byte. Store redacted mismatches with reproducible fixture IDs.

- [ ] **Step 3: Enforce ordered reversible cutover**

Enable CLI and Omni, then Telegram, then Web Chat/operator UI using per-channel config flags. Each stage requires contract suite pass, zero unexplained migration differences, rollback command tested, and an observation window meeting configured error/latency/duplicate-effect thresholds. A failed threshold automatically restores the previous ingress flag; it never rolls back durable data.

- [ ] **Step 4: Guard legacy retirement**

`RetirementChecker.authorize(component)` must require zero callers from static/runtime inventory, parity pass, reconciliation pass, rollback artifact, full suite pass, completed observation window, and signed release record. Retirement changes are separate commits after authorization; data stores/media remain retained per migration policy.

- [ ] **Step 5: Verify and commit**

```powershell
uv run pytest tests/hermes_personal/cutover -q
git add -- hermes_personal/cutover tests/hermes_personal/cutover docs/hermes-personal/cutover-runbook.md
git commit -m "feat: guard hermes channel cutover"
```

Expected: parity/retirement suites pass.

### Task 8: Run Full Offline Acceptance And Operational Smoke Tests

**Files:**
- Create: `tests/hermes_personal/e2e/test_four_channel_orchestration.py`
- Create: `tests/hermes_personal/e2e/test_supervisor_recovery.py`
- Create: `tests/hermes_personal/e2e/test_security_boundaries.py`
- Create: `docs/hermes-personal/operations.md`

**Interfaces:**
- Consumes: the complete Gates 1-7 runtime with fake external providers.
- Produces: final acceptance evidence for production observation.

- [ ] **Step 1: Prove four-channel orchestration**

Run equivalent natural-language requests through Telegram, CLI, Web, and Omni fixtures; verify one upstream agent boundary, structured clarification for ambiguity, stable capability selection, shared workflow/approval state, channel-local histories, and explicit cross-channel handoff.

- [ ] **Step 2: Prove restart safety**

Kill fake Gateway, API, worker, MCP monitor, and Web children independently. Verify bounded restart, readiness transitions, workflow/approval persistence, event replay, expired lease recovery, no duplicate paid effect, and clean supervisor shutdown.

- [ ] **Step 3: Prove security and failure behavior**

Test owner isolation, forged principal rejection, stale command version, duplicate idempotency, secret redaction, MCP outage, provider schema error, budget rejection, changed artifact approval invalidation, and no natural-language bypass/static fake progress.

- [ ] **Step 4: Run all verification**

```powershell
uv run pytest tests/hermes_personal -q
uv run pytest tests/tools/test_registry.py tests/tools/test_mcp_capability_gating.py tests/gateway/test_session.py -q
uv build --wheel
uv run hermes start --help
git diff --check
```

Expected: both pytest commands exit `0`; wheel builds; CLI help exits `0`; diff check is empty. Record exact counts and wheel path in the execution report.

- [ ] **Step 5: Run local smoke without paid providers**

Start with fake-provider profile, wait for `/health/ready`, submit one Web Agent Turn, observe real events, stop with CTRL-C, and verify no child process remains. Use Playwright desktop/mobile screenshots to confirm the Web workflow view renders real state without overlap or fake assets.

- [ ] **Step 6: Commit final acceptance artifacts**

```powershell
git add -- tests/hermes_personal/e2e docs/hermes-personal/operations.md
git commit -m "test: complete hermes orchestrator cutover acceptance"
```

## Gate 7 Exit Criteria

- `hermes start` validates, recovers, discovers, starts, supervises, and stops the complete runtime.
- Web is available in development and production modes; readiness reflects mandatory dependencies.
- Process restart does not lose workflow, approval, event, job, budget, or learning state.
- All four channels use one natural-language brain and shared deterministic application plane.
- Web/Telegram show real durable events and artifact refs only.
- Correlation is complete and secrets/sensitive payloads are redacted.
- Shadow parity, reconciliation, rollback, observation, and retirement guards pass.
- Full offline compatibility/contract/workflow/security/E2E suites pass without live paid-provider calls.
