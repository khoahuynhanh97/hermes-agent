# Hermes Personal Live Integration Implementation Plan

> **For agentic workers:** Use the available `executing-plans` or `subagent-driven-development` skill. Execute only the task assigned by Current Next Action in the SSOT; do not run the entire roadmap automatically.

**Goal:** Close the observed local integration gaps before obtaining genuine, durable Product Intelligence to Video Factory happy-path evidence.

**Architecture:** Keep the canonical Gateway, SQLite workflow/outbox, and existing MCP adapters. Repair process bootstrap/readiness and actual PI contracts at their current boundaries. Separate offline code acceptance from external-source remediation, controlled discovery, and paid live acceptance.

**Tech Stack:** Python, FastAPI/ASGI, SQLite, existing Hermes ToolRegistry, MCP, pytest, PowerShell.

## Global Constraints

- Working repository: `D:/work/hermes-upstream-rearchitecture`.
- Sole scheduling/status authority: `D:/work/hermes-upstream-rearchitecture/.hermes/coordination.md`. This plan specifies work, not ownership.
- Scope: PERSONAL_HAPPY_PATH_V1, one machine, one owner, SQLite.
- Baseline: HEAD `2a4c8e98b1`, Worker 103 code `946ecf964a`, accepted by Review 105.
- Previously accepted Iteration 96, outbox wiring, body-limit and IP rate-limit fixes remain accepted. No unrelated hardening or refactor.
- Planner writes planning/coordination only, never runs tests/Python/runtime/build/providers.
- Worker may run only the assigned focused offline tests, scoped lint, and diff-check. No full suite/build/package installation.
- Preserve all existing staged/unstaged/untracked changes, including `.agents/reports/`, `a.txt`, `b.txt`, `c.txt`. No reset, clean, broad staging, or restoring old coordination.
- Do not launch/import external PI/VF servers, call providers, broadly discover all MCP servers, edit user config/secrets, or run a live gateway/worker for verification.
- External PI source at `D:/work/Personal/Product-Intelligence/product_scout/mcp_server.py` is read-only for this assignment. External repository changes need a separately scoped authorization.
- Local focused tests use temporary Hermes home/SQLite and prevent external dispatch. Do not instantiate a live AIAgent.
- Real records, IDs and assets must remain distinguishable from offline fixtures. Fixture passing is not MVP_DONE.
- HA, distributed workers, multi-tenant controls and generalized process hardening remain HARDENING_DEFERRED.

## Source Evidence and Review Boundaries

- Gateway `main()` does not pass `tool_registry`; configured readiness requires it.
- Supervisor Gateway probe uses `/healthz`, whose response currently claims ready unconditionally.
- Worker/Gateway bootstrap falls back to `Path.home() / ".hermes"`, unlike canonical `get_hermes_home()` on Windows.
- PI adapter sends `keywords/pdp_url`, `research_result`, `pack_dict`. Located server accepts `url/query`, `snapshot_id`, `resource_pack_id`.
- Located PI `lock_resource_pack()` constructs synthetic assets, `example.com` provenance and fixed `snap_001/prod_001`; it is not a verified real-asset bridge.
- VF module `mcp_servers.video_factory.server` was absent at the checked repo/src/site-packages locations. Do not infer whole-machine absence.
- `known-gaps.md`, early runbook sections and the untracked runtime report disagree with later code/SSOT. Documentation is evidence to reconcile, not authority to reopen accepted code.

## Execution and Ownership

- [x] Task 1: Bootstrap, readiness and home consistency. CURRENT WORKER ASSIGNMENT.
- [ ] Task 2: PI adapter contract and durable identifiers. Await Task 1 review/assignment.
- [ ] Task 3: Reconcile current operator documentation. Await assignment.
- [ ] Task 4: Real PI provenance, VF source and controlled discovery gate. External/live prerequisites.
- [ ] Task 5: Authorized real happy-path acceptance. Paid approval required where applicable.

Use one worker iteration per assigned task, then hand off and exit. Task 1 touches Gateway home as well as readiness, so one file owner is preferable. Later independent source inspection may use a read-only subagent; never let two agents edit the same file or let subagents independently write SSOT.

## Task 1: Correct Bootstrap and Readiness at the Process Boundary

**Allowed files (relative to the working repository above):**
- Modify: `hermes_personal/runtime/gateway_server.py`
- Modify: `hermes_personal/runtime/processes.py`
- Modify: `hermes_personal/workflows/worker.py` (home resolution only)
- Tests: `tests/hermes_personal/runtime/test_startup_readiness_lifecycle.py`
- Tests: `tests/hermes_personal/runtime/test_gateway_server.py`
- Tests: `tests/hermes_personal/runtime/test_processes.py`
- Tests: `tests/hermes_personal/workflows/test_worker.py`
- Planning status: this file and SSOT only at handoff.
- Do not edit supervisor core, capability discovery rules, middleware, PI adapters or external source in this task.

**Interfaces:**
- Consume `hermes_constants.get_hermes_home() -> Path`.
- Consume existing `tools.registry.registry`; importing this registry module is not permission to load tool modules or launch discovery.
- Preserve `create_gateway_application(..., tool_registry: Any | None = None)`.
- Preserve `HealthAPI.handle_ready() -> tuple[int, dict[str, Any]]`.
- Produce bootstrap wiring to the already available in-process registry; actual selective MCP registration remains Task 4.

- [x] Add failing focused tests for the production entrypoint, not only the injectable factory. Monkeypatch `uvicorn.run`, supply a recording/fake agent, and provide an existing in-process offline registry. Assert the registry reaches catalog construction. Add empty-registry and populated-registry cases; no actual MCP discovery or provider call.
- [x] Add readiness equivalence and topology tests. A configured app with absent tools must return 503 through both `/health/ready` and the legacy `/healthz` compatibility endpoint. Fake mode remains explicitly ready. Assert the actual Gateway ProcessSpec uses `/health/ready`.
- [x] Add home tests with HERMES_HOME unset and explicit override: Gateway DB and worker dotenv/default DB resolve using canonical home. Mock CLI server/worker execution, use temp paths, and preserve explicit `--db-path` precedence.
- [x] Run only the four allowed test files below to record expected regression failures before changing code.
- [x] Apply minimal bootstrap wiring and home resolution. The intended integration points are:

```python
from hermes_constants import get_hermes_home

home = get_hermes_home()
database_path = Path(args.db_path) if args.db_path else home / "hermes.db"

tool_registry = None
if args.provider_mode == "configured":
    from tools.registry import registry
    tool_registry = registry

# Pass tool_registry=tool_registry into the existing factory call.
```

Worker `main()` also uses `home = get_hermes_home()` before dotenv/default DB resolution. Leave worker discovery behavior unchanged in this bounded task; tests must stub it before calling configured worker main.

- [x] Share the existing HealthAPI instance between canonical health routes and compatibility `/healthz`; never duplicate readiness logic:

```python
from fastapi.responses import JSONResponse

# health_api is the same instance passed to create_application().
@app.get("/healthz", include_in_schema=False)
def healthz() -> JSONResponse:
    status_code, body = health_api.handle_ready()
    return JSONResponse(status_code=status_code, content=body)
```

Set the Gateway ProcessSpec HTTP readiness endpoint to `/health/ready`. Do not broaden this into another supervisor rewrite.

- [x] Rerun the same focused tests and scoped lint:

```powershell
uv run pytest tests/hermes_personal/runtime/test_startup_readiness_lifecycle.py tests/hermes_personal/runtime/test_gateway_server.py tests/hermes_personal/runtime/test_processes.py tests/hermes_personal/workflows/test_worker.py -q
uv run ruff check hermes_personal/runtime/gateway_server.py hermes_personal/runtime/processes.py hermes_personal/workflows/worker.py tests/hermes_personal/runtime/test_startup_readiness_lifecycle.py tests/hermes_personal/runtime/test_gateway_server.py tests/hermes_personal/runtime/test_processes.py tests/hermes_personal/workflows/test_worker.py
git diff --check
```

Expected: assigned tests pass; lint/diff clean; zero actual MCP/provider calls. If imports depend on missing installed dependencies, report rather than installing packages.

- [x] Review diff; commit only task-owned paths if the working tree permits an isolated commit. Otherwise report exact uncommitted diff and why. Never stage unrelated files.
- [x] Report registry wiring versus discovery explicitly: an empty production registry correctly remains NOT_READY; this task does not establish live MCP readiness. Include command outputs/counts, file paths, commit/diff and remaining external blockers.
- [x] Mark Task 1 implemented pending Planner acceptance; hand off SSOT to PLANNER and exit. Do not start Task 2.

**Acceptance:** production entrypoint wiring exercised offline, compatibility health no longer lies, supervisor uses canonical readiness, Windows/default/explicit home coherence covered, prior fake/offline behavior retained. Do not fabricate healthy bindings or suppress failure to make startup green.

## Task 2: PI Contract and Durable Identifier Mapping

**Changes only after Planner assignment.**

**Files:** `hermes_personal/product_video/handlers.py`; create `tests/hermes_personal/product_video/test_pi_mcp_contract.py`; use focused existing outbox tests only if downstream artifact behavior changes.

**Read-only source:** `D:/work/Personal/Product-Intelligence/product_scout/mcp_server.py` and the resource-pack models/repository it delegates to.

**Interface contract to implement and verify:**

| Stage | Outgoing arguments for located PI server | Required preserved result |
| --- | --- | --- |
| research_product | product_name; url from pdp_url; query query-string derived from keywords | snapshot_id, persistence_status, full research result, original request provenance |
| build_resource_pack | snapshot_id, optional variant_id only when selected | resource_pack_id, canonical_product_id, pack_status, restrictions/completeness |
| lock_resource_pack | resource_pack_id, explicit owner_user_id | lock_id, resource_pack_id, version, manifest_digest and actual asset provenance |

- [x] Read exported server signatures as text/AST only; build strict signature fixtures locally without importing the external server. Fixtures must reject the old unexpected keywords and missing required IDs.
- [x] Write failing research -> build -> lock contract tests, including non-persisted research/missing snapshot_id, unknown resource pack, identity/owner mismatch and non-lockable pack state. Assert no downstream call when prerequisites fail.
- [x] Implement mapping in the existing PI adapter. Keep machine-readable snapshot_id outside serialized report text, and retain workflow/job provenance expected downstream. Use existing structured error handling; do not synthesize IDs or successful packs for missing provider data.
- [x] Carry exact resource-pack/lock identifiers through artifacts and restart serialization. Preserve the existing safe behavior for deliberately different custom adapters only through explicit contract selection, never speculative retry with alternative argument shapes after a possibly stateful tool call.
- [x] Confirm how actual assets/manifest are retrieved before accepting a locked result. Do not bless the located server's hard-coded example assets as additional evidence. If the genuine server contract cannot yet supply required artifacts, fail closed and report Task 4 dependency.
- [x] Run the new contract test file only, plus named existing outbox tests directly affected; specify node IDs in SSOT before widening verification. Scoped lint/diff-check and task-owned commit.
- [x] Hand off evidence and unresolved server-side provenance. Passing strict fixtures means adapter contract acceptance only, not live integration success.

## Task 3: Reconcile Operator Documentation

**Files:** `docs/known-gaps.md`, `docs/hermes-personal/operations.md`, `docs/hermes-personal/product-video-runbook.md`. Preserve the user's untracked report without editing it.

- [ ] Separate adapter/safety acceptance from live validation in HP-007/008/012 and triage summary; do not label all 15 items globally live-complete.
- [ ] Remove the obsolete in-memory-only budget and missing-worker claims using current source evidence.
- [ ] Replace the early runbook's assumed `$90` provider price and deterministic build fallback with reservation semantics and fail-closed behavior. Make home and provider-mode instructions consistent with actual bootstrap.
- [ ] Record the old report's absent-consumer finding as superseded by current `job.dispatch` producer/consumer wiring, in maintained documentation rather than altering the untracked report.
- [ ] Cite exact accepted code/report and list remaining PI/VF prerequisites. No fresh full audit or tests; use static checks and `git diff --check`.
- [ ] Hand off documentation-only diff.

## Task 4: Real PI Provenance and VF Source / Discovery Gate

This is a prerequisite gate, not blanket permission to modify another repository or execute servers.

- [ ] Identify intended VF repository/package/launch command from supplied source or bounded local metadata. If still missing, request that exact input without scanning the whole machine again.
- [ ] Inspect actual PI asset persistence/materialization and lock construction. Before an external PI fix, obtain authorization scoped to `D:/work/Personal/Product-Intelligence`, inspect its AGENTS/dirty state, and write its exact affected-file/test assignment into SSOT.
- [ ] Require lock output to derive from a persisted selected pack, with real canonical product/snapshot/asset IDs, source provenance, valid artifact locations and deterministic manifest integrity; no fixed prod_001/snap_001/example.com records or fabricated physical assets.
- [ ] Review PI and VF startup imports, tool schemas, config paths, persistent directories and subprocess behavior statically.
- [ ] Specify exactly which PI/VF processes may be started, isolated temporary home/state directories, maximum 30-second discovery deadline per process, cleanup/termination procedure and zero tool-execution/spending budget. Verify registration does not initiate acquisition/generation at startup. If it does, do not execute.
- [ ] Only after explicit scoped discovery authorization, run selective schema discovery for those two servers and required tools, not all six configured servers. Registration must occur in the consuming Gateway/worker process or through an existing supported lifecycle; no assumed shared globals across independent processes.
- [ ] Validate the capability names required by catalog readiness without injecting fake learning bindings or weakening mandatory readiness to force green.
- [ ] Report exact schemas, names, registration results and cleanup evidence with secrets redacted. No generation/render/export/publish permission follows from discovery approval.

**Gate:** actual contracts and startup safety established; isolated discovery successful if authorized; real PI provenance available. Missing external inputs become an explicit BLOCKED report, never silent fixture substitution.

## Task 5: Authorized Real Happy-Path Acceptance

- [ ] Obtain intended provider, locally confirmed credential availability, exact approved monetary cap/currency and allowed operations. Secret values never go into chat, reports or source.
- [ ] Fix one owner, one explicit home/SQLite DB and one selected product input. Record configuration fingerprints without secrets and establish backup/cleanup boundaries.
- [ ] Under the approved cap, run research -> resource pack -> lock -> brief -> scene -> storyboard -> render -> export with all five human approvals respected.
- [ ] Record real provider job IDs, immutable input/output references, actual readable non-empty video artifact, and ledger reservation/commit/release evidence. A URL string or mock job ID alone is insufficient.
- [ ] Perform only the authorized restart/resume check at a safe boundary: workflow state, approval and artifact references survive; uncertain remote outcomes reconcile or halt rather than blindly resubmit paid work.
- [ ] Planner reviews real evidence and chooses MVP_DONE only after all personal-path criteria pass. Keep production hardening deferred and stop the automation only when its purpose is completed or the user stops it.

## Handoff Protocol

Before any SSOT write, reread the entire file and compare hash, owner and worker marker to the starting snapshot. Cancel on mismatch rather than overwrite another actor. Only the main worker writes Last Worker Report, both owner fields and History; keep prior Planner review/history. Check no old worker is still editing after handoff before dispatching a subsequent iteration.

Current authorized dispatch: Task 1 only, Worker 104 / Planner Review 106. Subsequent tasks are roadmap, not permission to bypass review or external/paid gates.
