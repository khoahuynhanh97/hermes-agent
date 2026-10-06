# Hermes Canonical Personal Assistant Full Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task with a Planner review after every task. Do not run tasks concurrently because later cleanup depends on proven caller migration.

**Goal:** Converge the repository on one upstream `run_agent.AIAgent` conversational brain while retaining Knowledge Base, Product Research, Video Factory, approvals, budgets, and durable workflows strictly as edge capabilities.

**Architecture:** Existing upstream CLI, gateway, Telegram plugin, TUI, desktop, skill discovery, MCP client, and `AIAgent` remain canonical. `HermesTurnService` may survive only as a thin channel-neutral contract/facade while callers are migrated; it must not own another model loop, prompt builder, tool router, memory system, or session brain. Knowledge, research, and video execution are exposed through governed skills plus service-gated tools or MCP, while SQLite workflows own only durable state, approvals, retries, and restart recovery.

**Tech Stack:** Python, upstream Hermes plugin/skill/MCP infrastructure, FastMCP, SQLite, existing gateway platform plugins, PowerShell, Git.

## Global Constraints

- Preserve every pre-existing tracked and untracked worktree change.
- Never use destructive Git commands, broad checkout/reset, or delete an item classified `UNKNOWN`.
- `run_agent.AIAgent` is the only conversational/model-execution brain.
- Do not create a second runtime, gateway, conversation loop, prompt builder, memory platform, tool router, or capability catalog.
- Keep the system prompt byte-stable during a conversation; skills enter as user messages through the existing skill-command path.
- Use the existing Footprint Ladder: existing seam, then CLI command + skill, service-gated tool, plugin, or MCP. Do not add personal model tools to the permanent core schema.
- `.agents/skills/**` is governed project skill source. Do not copy it into repository `skills/**` or runtime `~/.hermes/skills/**` unless the existing installer/discovery mechanism explicitly performs that operation.
- Knowledge candidates require human approval; retrieval returns approved knowledge only.
- Product Lock, Brief, Scene Plan, Storyboard, Render Budget, and Final Export remain fail-closed HITL gates.
- Paid calls require a positive durable budget authorization before invocation; uncertain provider outcomes must not be blindly retried.
- Do not call paid providers, send production Telegram messages, publish media, or use real customer credentials during implementation.
- Per operator request, do not create or modify tests and do not run pytest, unit, integration, E2E, or full suites.
- Allowed verification is read-only/static or offline smoke only: `rg`, imports, CLI help, skill discovery, MCP `tools/list`, configuration parsing, `git diff --check`, and `git status`.
- Because tests are excluded, final status must be `IMPLEMENTED_UNVERIFIED`, never `TESTED`, `PRODUCTION_READY`, or full `PERSONAL_HAPPY_PATH_V1_ACCEPTED`.
- Commit each task separately. Stage only files owned by that task.

---

### Task 0: Close ARCH-G2-R1 Evidence Correction

**Files:**
- Modify: `reports/personal-assistant-architecture/canonical-ownership-matrix.csv`
- Modify: `reports/personal-assistant-architecture/runtime-removal-candidates.md`
- Modify: `reports/personal-assistant-architecture/target-runtime-flow.md`
- Modify: `reports/personal-assistant-architecture/happy-path-gap-matrix.md`
- Modify: `reports/personal-assistant-architecture/next-implementation-slice.md`
- Modify: `.hermes/coordination.md`
- Remove only if Worker created it and its contents have been merged: `reports/personal-assistant-architecture/evidence-ledger.md`

**Produces:** A trustworthy ownership baseline and Planner handoff; no source behavior change.

- [ ] Separate dispatch commit `55ebe92e00`, source baseline `b193b1d07e`, rework start `b6bcfc109e`, and current report commit `9f639125a1`.
- [ ] Replace wildcard/nonexistent Telegram references with exact files and symbols under `plugins/platforms/telegram/**`.
- [ ] Remove nonexistent `hermes_personal/product_video/toolset.py` claims and record exact callers of product/video adapters.
- [ ] Mark Knowledge classes without production callers `DECLARED_ONLY` or `UNKNOWN`, never integrated/confirmed.
- [ ] Replace stale `skills/hermes-personal-*` proposals with the verified `.agents/skills/**` project-discovery seam.
- [ ] Remove every `file://` link and every recommendation to extend `hermes_personal/runtime/supervisor.py`.
- [ ] Rewrite `next-implementation-slice.md` as the sequence in Tasks 1-10 below.
- [ ] Put exact evidence commands/results inside one of the five allowed reports; do not leave a sixth untracked ledger.
- [ ] Update coordination to `AWAITING_PLANNER_REVIEW`, owner `PLANNER`, without erasing history.
- [ ] Run `git diff --check` and inspect `git status --short`.
- [ ] Commit reports, then commit coordination separately.

### Task 1: Freeze the Canonical Ownership Decision

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/README.md`
- Modify: `docs/hermes-personal/gateway.md`
- Modify: `docs/hermes-personal/capabilities.md`
- Modify: `docs/hermes-personal/workflows.md`
- Modify: `docs/known-gaps.md`
- Modify: `reports/personal-assistant-architecture/target-runtime-flow.md`

**Produces:** One normative ownership contract used to judge all following changes.

- [ ] Declare `run_agent.AIAgent.run_conversation()` the sole model/tool conversation loop.
- [ ] Define upstream CLI, TUI, desktop/serve, gateway, and platform plugins as ingress surfaces that reuse the same upstream agent lifecycle.
- [ ] Define `HermesTurnService` as a temporary thin facade only: normalize `AgentTurnRequest`, resolve durable identity/session references, call the supplied upstream agent, and project `AgentEvent` results.
- [ ] Explicitly forbid `HermesTurnService` from building system prompts, selecting providers, maintaining a second transcript, routing domain intent, or executing tools itself.
- [ ] Define Knowledge, Product Research, and Video Factory as edge capability owners; define workflows as durable sequencing/state only.
- [ ] Document `src/hermes/**` as a migration source, not an accepted package boundary.
- [ ] Reconcile wording that currently calls both `HermesTurnService` and `AIAgent` canonical: canonical turn contract/facade is not a second brain.
- [ ] Commit: `docs(architecture): freeze canonical assistant ownership`.

### Task 2: Converge All Conversational Ingress on Upstream AIAgent

**Files:**
- Modify only after preserving current user diff: `cli.py`
- Modify only after preserving current user diff: `gateway/run.py`
- Modify: `hermes_personal/gateway/plugin.py`
- Modify: `hermes_personal/orchestration/turn_service.py`
- Modify: `hermes_personal/orchestration/upstream_agent.py`
- Modify: `hermes_personal/application/turn_api.py`
- Modify: `hermes_personal/application/app.py`
- Later cleanup candidate, not yet delete: `hermes_personal/runtime/gateway_server.py`

**Consumes:** Task 1 ownership contract.

**Produces:** Every natural-language ingress reaches an upstream session-scoped `AIAgent`; no personal model loop.

- [ ] Inventory exact production callers before editing and record them in the ownership matrix.
- [ ] Reuse the upstream gateway/session agent factory instead of constructing a parallel personal agent cache.
- [ ] Make the personal facade accept/invoke an already-owned upstream agent/session boundary.
- [ ] Remove domain-intent selection and capability routing from the conversational turn path.
- [ ] Keep `AgentTurnRequest` and `AgentEvent` as channel-neutral wire contracts.
- [ ] Do not reimplement TUI, desktop, dashboard, Telegram, or CLI chat surfaces.
- [ ] Offline smoke: import touched modules and run CLI/gateway help only.
- [ ] Commit: `refactor(personal): converge ingress on upstream agent`.

### Task 3: Make Governed Skills the Only User-Facing Playbooks

**Files:**
- Modify: `.agents/skills/hermes-personal-knowledge-learning/SKILL.md`
- Modify: `.agents/skills/hermes-personal-product-research/SKILL.md`
- Modify: `.agents/skills/hermes-personal-product-video-production/SKILL.md`
- Create only if required for the three Vietnamese entry commands: `.agents/skills/hoc/SKILL.md`
- Create only if required: `.agents/skills/hoc-kien-thuc/SKILL.md`
- Create only if required: `.agents/skills/hoc-cta/SKILL.md`
- Modify only if a generic alias seam is demonstrably missing: `agent/skill_commands.py`
- Reconcile existing user changes without overwriting: `hermes_cli/commands.py`
- Reconcile existing user changes without overwriting: `hermes_cli/cli_commands_mixin.py`

**Produces:** `/hoc`, `/hoc_kien_thuc`, and `/hoc_cta` resolve to skill user messages, never special conversation handlers or system-prompt mutations.

- [ ] Prove `.agents/skills/**` is visible through trusted project discovery before adding any loader behavior.
- [ ] Prefer three small governed alias/playbook skills over new core slash-command handlers.
- [ ] Keep stable capability IDs authoritative; wire tool names remain dynamically resolved bindings.
- [ ] Remove or avoid direct `/hoc*` branches in `cli.py` and `gateway/run.py` when skill-command dispatch already covers them.
- [ ] Ensure commands are not embedded into past conversation context and do not rebuild the system prompt.
- [ ] Offline smoke: list discovered skill commands in a temporary trusted project/profile without model calls.
- [ ] Commit: `feat(skills): expose governed personal playbooks`.

### Task 4: Wire Knowledge as an Approved Edge Capability

**Files:**
- Modify: `hermes_personal/learning/repository.py`
- Modify: `hermes_personal/learning/retrieval.py`
- Modify: `hermes_personal/learning/promotion.py`
- Modify: `hermes_personal/learning/context.py`
- Modify: `hermes_personal/learning/skill_publisher.py`
- Modify: `hermes_personal/storage/sqlite.py`
- Create or modify the existing personal MCP/plugin binding under `hermes_personal/integrations/**`; do not add a core tool.
- Modify: `.agents/skills/hermes-personal-knowledge-learning/SKILL.md`

**Produces:** Structured `knowledge.candidate.create` and `knowledge.retrieve` capability calls with SQLite durability and approval enforcement.

- [ ] Add one edge registration seam exposing candidate creation and approved-only retrieval.
- [ ] Persist candidates before returning success; default state is `review_required`.
- [ ] Reject implicit/automatic promotion and retrieval of raw, rejected, failed, or unapproved material.
- [ ] Use `AgentContextAssembler` only if upstream calls it through a bounded pre-turn context extension that preserves stable prompt caching; otherwise remove the claim that it is integrated and use explicit retrieval results in the current turn.
- [ ] Keep `ProceduralSkillPublisher` out of the active skill tree until an approved publication transaction succeeds.
- [ ] Offline smoke: import server/plugin, call MCP `tools/list`, and inspect a temporary SQLite schema without writing to the user profile.
- [ ] Commit: `feat(knowledge): expose approved edge capabilities`.

### Task 5: Wire Product Research Through the Existing External MCP Seam

**Files:**
- Modify: `hermes_personal/integrations/product_intelligence/client.py`
- Modify: `hermes_personal/integrations/product_intelligence/contracts.py`
- Modify: `hermes_personal/product/research.py`
- Modify: `hermes_personal/product/resource_pack.py`
- Modify: `hermes_personal/product_video/handlers.py`
- Modify: `.agents/skills/hermes-personal-product-research/SKILL.md`
- Modify: `.agents/skills/hermes-personal-product-video-production/SKILL.md`
- Modify documented/configured MCP catalog entry only; do not copy `D:/work/Personal/Product-Intelligence` into this repository.

**Produces:** Real capability discovery and provenance-preserving resource packs; no fabricated production research.

- [ ] Treat Product Intelligence as an external MCP dependency with explicit unavailable/degraded errors.
- [ ] Resolve capability IDs to current discovered wire tools; do not hard-code stale wire names as policy truth.
- [ ] Remove the production fallback that fabricates values such as `42% market potential`; if fake mode remains, require an explicit local-development flag and label every output fake.
- [ ] Persist source URLs, observation timestamps, raw snapshot IDs, digests, and lock/version identifiers.
- [ ] Fail closed when a resource pack is incomplete, unreviewed, unlocked, or cannot be reloaded after restart.
- [ ] Offline smoke: MCP `tools/list` and schema inspection only; do not execute web/provider research.
- [ ] Commit: `feat(product): bind research through external MCP`.

### Task 6: Consolidate Video Factory Into One Packaged Edge Capability

**Files:**
- Migration source: `src/hermes/domain/video_factory.py`
- Migration source: `src/hermes/application/video_factory_service.py`
- Migration source: `src/hermes/adapters/sqlite/video_factory_repository.py`
- Migration source: `src/hermes/adapters/google/vertex_video_provider.py`
- Migration source: `src/hermes/mcp/video_factory/server.py`
- Target: focused modules under `hermes_personal/video_factory/**` or an existing first-party plugin package selected in Task 1; use exactly one target, not both.
- Modify: `hermes_personal/integrations/video_factory/client.py`
- Modify: `hermes_personal/integrations/video_factory/contracts.py`
- Modify: `hermes_personal/product_video/handlers.py`
- Modify: `pyproject.toml`

**Produces:** One importable, packaged, independently started Video Factory MCP edge server using the already accepted Vertex/Veo provider implementation.

- [ ] Select the target by existing package ownership: because `hermes_personal` is already included, prefer a bounded `hermes_personal.video_factory` package unless plugin discovery provides a smaller proven seam.
- [ ] Move/refactor domain, repository, provider, service, and MCP registration without changing the proven Vertex request/poll/export semantics from `d4eeafc5bd`.
- [ ] Add one explicit executable/launch target and one canonical import path.
- [ ] Migrate all in-repository callers and config references to the canonical path.
- [ ] Keep provider credentials secret-only; place behavioral settings in `config.yaml`, not new environment variables.
- [ ] After `rg` proves zero production callers/imports, remove the orphaned `src/hermes/**` copy in a separate commit.
- [ ] Offline smoke: import the canonical server and invoke MCP `tools/list`; never render or call Vertex.
- [ ] Commit migration: `refactor(video): package video factory edge capability`.
- [ ] Commit orphan removal: `refactor(video): remove obsolete src hermes copy`.

### Task 7: Keep Workflow, HITL, Outbox, and Budget as Durable Support Only

**Files:**
- Modify: `hermes_personal/product_video/workflow.py`
- Modify: `hermes_personal/product_video/handlers.py`
- Modify: `hermes_personal/workflows/engine.py`
- Modify: `hermes_personal/workflows/approvals.py`
- Modify: `hermes_personal/workflows/budgets.py`
- Modify: `hermes_personal/workflows/jobs.py`
- Modify: `hermes_personal/workflows/outbox_repository.py`
- Modify: `hermes_personal/workflows/outbox_dispatcher.py`
- Modify: `hermes_personal/workflows/recovery.py`
- Modify: `hermes_personal/workflows/worker.py`

**Produces:** Durable workflow support with no semantic conversation routing.

- [ ] Restrict workflow definitions to stage state, preconditions, idempotency keys, retry policy, artifact references, approvals, and recovery.
- [ ] Enforce Product Lock → Brief approval → Scene Plan approval → Storyboard approval → render budget approval → Final approval/export.
- [ ] Reserve budget durably before paid dispatch, settle exactly once on confirmed outcome, and require operator reconciliation for unknown outcomes.
- [ ] Ensure no no-op/logger handler ACKs durable work.
- [ ] Make every outbox topic have a concrete producer and consumer or mark it unsupported; never report readiness for an unbound topic.
- [ ] Keep the worker independent of the conversational loop and incapable of choosing user intent.
- [ ] Offline smoke: start worker in an isolated temporary home with zero paid bindings, inspect readiness, then stop it.
- [ ] Commit: `fix(workflows): enforce durable HITL and budget boundaries`.

### Task 8: Integrate Telegram Approval Through a Generic Upstream Boundary

**Files:**
- Modify only generic platform behavior if necessary: `plugins/platforms/telegram/adapter.py`
- Modify: `plugins/platforms/telegram/__init__.py`
- Modify or create personal plugin callback binding under `hermes_personal/gateway/**`
- Modify: `hermes_personal/workflows/approvals.py`

**Produces:** Telegram can present and resolve durable approvals without importing Product Video domain logic into the platform adapter.

- [ ] Trace the actual callback registration symbol and lifecycle before editing.
- [ ] Keep the Telegram adapter generic: decode signed callback identity and dispatch a generic approval response/event.
- [ ] Put workflow ID, approval ID, owner ID, expiry, and nonce/signature validation in the bounded personal handler.
- [ ] Reject wrong owner, expired, replayed, unknown, or already-resolved callbacks.
- [ ] Do not send a production Telegram message; use registration/import/config inspection only.
- [ ] Commit: `feat(approvals): bridge telegram to durable approval boundary`.

### Task 9: Retire Duplicate Runtime Surfaces After Caller Migration

**Files/Candidates:**
- `hermes_personal/runtime/gateway_server.py`
- `hermes_personal/runtime/supervisor.py`
- `hermes_personal/runtime/startup.py`
- `hermes_personal/runtime/processes.py`
- `hermes_personal/runtime/readiness.py`
- `hermes_personal/runtime/cli.py`
- `hermes_personal/orchestration/upstream_agent.py`
- `hermes_personal/capabilities/service.py`
- `hermes_personal/capabilities/policy.py`
- `hermes_personal/cutover/**`
- `hermes_personal/api/**`

**Produces:** No second production gateway/runtime/catalog remains; retained modules have a documented bounded purpose and real caller.

- [ ] For every candidate, record `production callers`, `replacement`, `data/state migration`, and `KEEP/DEPRECATE/REMOVE/UNKNOWN`.
- [ ] Do not remove `UNKNOWN`; prove absence with exact imports, entry points, config, docs, scripts, and package references.
- [ ] Remove personal agent factory/cache, supervisor/start topology, gateway server, and catalog only after upstream replacements own every production caller.
- [ ] Retain SQLite workflow/approval/budget processes only as edge services and give them capability-specific names/entry points.
- [ ] Remove compatibility adapters only after no production caller remains; do not keep dead shims indefinitely.
- [ ] Run repository-wide `rg` after each deletion and inspect imports with isolated Python commands.
- [ ] Commit one coherent removal group at a time using `refactor(personal): retire <surface>`.

### Task 10: Reconcile Packaging, Configuration, Documentation, and Handoff

**Files:**
- Modify: `pyproject.toml`
- Modify relevant sample/config documentation; do not add non-secret `HERMES_*` settings.
- Modify: `docs/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/hermes-personal/**`
- Modify: `docs/known-gaps.md`
- Modify: all five `reports/personal-assistant-architecture/**` artifacts
- Modify: `.hermes/coordination.md`

**Produces:** Install/runtime truth matches documentation and the Planner receives an evidence-backed unverified implementation.

- [ ] Confirm package inclusion and executable entry points for every retained runtime/capability.
- [ ] Confirm no config or docs reference `src/hermes`, removed personal runtime commands, nonexistent Telegram paths, or copied skill paths.
- [ ] Confirm upstream surfaces resolve the same governed skills and MCP capability configuration.
- [ ] Run only the permitted checks:

```powershell
git diff --check
git status --short
rg -n "src/hermes|hermes_personal/runtime/gateway_server|skills/hermes-personal|gateway/platforms/telegram.py|42% market potential" . --glob '!reports/**' --glob '!docs/superpowers/plans/**'
uv run python -c "from run_agent import AIAgent; print(AIAgent.__name__)"
uv run python -m hermes_cli.main --help
```

- [ ] Run isolated, non-business MCP `tools/list` for Knowledge, Product Intelligence, and Video Factory; do not call capability tools.
- [ ] Update evidence labels strictly: runtime/import/subprocess observed, static-only, historical test evidence, and unknown must remain distinct.
- [ ] Record skipped tests and state explicitly that no live provider, publish, or Telegram acceptance was performed.
- [ ] Set `.hermes/coordination.md` to owner `PLANNER`, status `AWAITING_PLANNER_REVIEW`, result `IMPLEMENTED_UNVERIFIED`.
- [ ] Commit: `docs(coordination): hand off canonical assistant implementation`.

## Planner Acceptance Gates

Planner must reject the handoff if any condition below is true:

1. More than one model/conversation loop or prompt owner remains reachable in production.
2. Any personal capability is permanently added to the core model-tool schema without a proven exception.
3. `/hoc*` requires system-prompt mutation or dedicated CLI/gateway conversation routing.
4. Knowledge can be auto-approved or unapproved knowledge can be retrieved.
5. Product research can silently fabricate production evidence.
6. Video Factory still has two active implementations or `src/hermes` remains the only runtime path.
7. A paid operation can start without durable positive budget approval.
8. A workflow can bypass any required HITL gate or ACK through a no-op handler.
9. Telegram platform code directly imports Product Video domain/workflow implementations.
10. Deleted code was `UNKNOWN`, still had production callers, or lost durable data/state.
11. Existing unrelated dirty files were overwritten, staged, or committed.
12. The Worker claims `TESTED`, `PRODUCTION_READY`, or full happy-path acceptance despite the no-test instruction.

## Required Final Worker Report

- Starting HEAD and ending HEAD.
- Commit hash for every task.
- Exact files changed, moved, and removed per commit.
- Canonical ownership map after implementation.
- Static caller evidence for every removed/retained duplicate candidate.
- Offline smoke commands and raw outcomes.
- Tests skipped explicitly by operator instruction.
- Remaining `UNKNOWN` and deferred risks.
- Final evidence level: `IMPLEMENTED_UNVERIFIED`.
- Current Owner: `PLANNER`; Assignment Status: `AWAITING_PLANNER_REVIEW`.
