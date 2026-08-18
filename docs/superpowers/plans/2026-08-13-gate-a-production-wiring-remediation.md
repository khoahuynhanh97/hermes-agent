# Gate A Production Wiring Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Gate A by replacing inferred security policy with explicit capability metadata, using one atomic MCP registration pipeline, and proving authenticated principal propagation through every production channel boundary.

**Architecture:** Channels authenticate and bind `PrincipalContext`; `AIAgent` consumes that context without inventing channel identity. `ToolRegistry` remains the only dispatcher and enforces the immutable `CapabilityDescriptor` stored on each `ToolEntry`. Native policy is resolved from an explicit exact-name/toolset policy inventory, while MCP descriptors come from server registration provenance. Live discovery, cache restore, and refresh all emit the same `RegistrationCandidate` type and pass through one validate-then-commit pipeline.

**Tech Stack:** Python 3.10+, ContextVar, dataclasses, aiohttp, FastMCP/MCP SDK, PyYAML, pytest, native PowerShell.

**Required worker context:** Before editing, read
`docs/superpowers/specs/2026-08-13-gate-a-worker-context-and-runtime-flow.md`.
It documents the existing call paths and behaviors that this plan must preserve.

## Global Constraints

- Do not modify `agent/conversation_loop.py`.
- Do not begin Gate B.
- Do not commit until Gate A receives reviewer approval.
- Preserve unrelated user changes, especially `test_vertex_ai.py`, `scratch/`, `scripts/`, and live-media artifacts.
- Do not import Product Intelligence packages or read its database from Hermes.
- Do not call live or paid providers.
- Do not infer owner, trust, principal mode, approval, or side effects from tool-name substrings.
- Do not create a second dispatch registry; capability policy is metadata consumed by `tools.registry`.
- Do not use `default_owner`, chat ID as actor identity, or implicit admin roles.

---

## Target Structure

```text
Channel authentication
  CLI / One-shot / Gateway / API / Telegram / GUI
                    |
                    v
        hermes.security.ingress
        PrincipalContext + principal_scope
                    |
                    v
          AIAgent.run_conversation
       consumes existing context only
                    |
                    v
           ToolRegistry.dispatch
                    |
          ToolEntry.descriptor
                    |
      bind principal according to policy
                    |
                    v
               tool handler

Native registration                    MCP registration
        |                                      |
exact policy inventory             server provenance/config
        |                                      |
        +---------- CapabilityDescriptor ------+
                               |
                         ToolRegistry.register
```

```text
Live MCP list --------> collect_live_candidates ----+
Cached MCP manifest --> collect_cached_candidates --+--> validate_candidates
Refresh list ---------> collect_live_candidates ----+             |
                                                                  v
                                                        atomic commit to registry
```

## Ownership Rules

| Component | Owns | Must not own |
| --- | --- | --- |
| Channel adapter | Authentication, actor mapping, platform/session identity | Tool policy or model routing |
| `hermes.security` | Principal model and scoped context lifecycle | Channel authentication |
| Capability policy | Immutable metadata and registration provenance | Handler execution |
| `tools.registry` | Atomic tool registration and dispatch enforcement | User authentication |
| `tools.mcp_tool` | MCP candidate collection, validation, registration | Hermes conversation logic |
| Skill validator | Static validation against a supplied coherent snapshot | Tool discovery or MCP process startup |

### Task 1: Make Capability Metadata Explicit at Registration

**Files:**
- Modify: `hermes/capabilities/models.py`
- Modify: `hermes/capabilities/catalog.py`
- Create: `hermes/capabilities/policies.py`
- Modify: `tools/registry.py`
- Modify: `tools/mcp_tool.py`
- Modify: `hermes/runtime_layout.py`
- Test: `tests/hermes/test_capability_catalog.py`
- Create: `tests/tools/test_capability_registration.py`

**Interfaces:**
- Produces: `CapabilityPolicyResolver.resolve_native(name, toolset)` and `CapabilityPolicyResolver.resolve_mcp(server_name, server_config, wire_name)`.
- Produces: `ToolRegistry.register(..., descriptor: CapabilityDescriptor | None = None)` with a descriptor stored atomically on `ToolEntry`.
- Enforces: a model-visible tool without explicit or policy-resolved metadata is not dispatchable.

- [ ] **Step 1: Write failing registration coverage tests**

```python
def test_register_stores_explicit_descriptor(registry, read_descriptor):
    registry.register(
        name="read_probe",
        toolset="test",
        schema={"name": "read_probe"},
        handler=lambda args: "ok",
        descriptor=read_descriptor,
    )
    assert registry.get_entry("read_probe").descriptor is read_descriptor


def test_unclassified_model_visible_tool_fails_closed(registry):
    registry.register(
        name="unclassified_probe",
        toolset="unknown-toolset",
        schema={"name": "unclassified_probe"},
        handler=lambda args: "must-not-run",
    )
    result = registry.dispatch("unclassified_probe", {})
    assert "capability descriptor" in result


def test_registered_production_tools_have_descriptors(discovered_registry):
    missing = [
        entry.name for entry in discovered_registry.snapshot_entries()
        if entry.descriptor is None
    ]
    assert missing == []
```

- [ ] **Step 2: Run the tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_capability_registration.py tests\hermes\test_capability_catalog.py -q
```

Expected: the inventory test reports current production registrations without descriptors; the unclassified tool is currently inferred and dispatched instead of failing closed.

- [ ] **Step 3: Add an explicit policy resolver**

Use exact keys, never substring classification:

```python
@dataclass(frozen=True)
class CapabilityPolicy:
    owner: str
    source: str
    trust: str
    side_effects: str
    principal_mode: str
    idempotency: str
    approval_policy: str
    data_classification: str


class CapabilityPolicyResolver:
    def resolve_native(self, name: str, toolset: str) -> CapabilityDescriptor | None: ...
    def resolve_mcp(
        self,
        server_name: str,
        server_config: dict,
        wire_name: str,
    ) -> CapabilityDescriptor: ...
```

`policies.py` contains exact tool overrides plus exact toolset defaults for existing native registrations. Unknown toolsets return `None`. MCP policy comes from a validated `capability` block in server config. External MCP defaults are safe and explicit: owner is the configured server name, source is `external_mcp`, trust is `configured_external`, principal mode is `none`, and side effects are `external`. Managed Hermes MCP entries receive an explicit capability block from `normalize_hermes_config`; do not identify them through a hard-coded name set inside dispatch.

- [ ] **Step 4: Resolve and store metadata during registration**

`ToolRegistry.register()` resolves native metadata before constructing `ToolEntry`. MCP call sites pass descriptors built from server provenance. Remove the dispatch-time call to `CapabilityCatalog.from_registry_snapshot(self._tools)`. Dispatch reads only `entry.descriptor`; missing metadata returns a permission error before invoking the handler.

- [ ] **Step 5: Make catalog a projection, not an inference engine**

`CapabilityCatalog.from_registry_snapshot()` copies explicit descriptors from a stable registry snapshot. It must raise on conflicting descriptors and must not catch `ValueError` with `pass`. Remove managed-server hard-coding and name-based source classification from the runtime path. Keep any legacy inference helper private and unused by dispatch, then remove it once characterization tests show no caller remains.

- [ ] **Step 6: Verify GREEN and inventory coverage**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_capability_registration.py tests\hermes\test_capability_catalog.py tests\hermes\test_principal_ingress.py -q
```

Expected: every discovered production tool has an immutable descriptor; unclassified registration is retained for diagnostics but cannot dispatch.

### Task 2: Replace MCP Registration Variants with One Candidate Pipeline

**Files:**
- Modify: `tools/mcp_tool.py`
- Modify: `tools/mcp_schema_cache.py`
- Modify: `tests/tools/test_mcp_tool_security.py`
- Create: `tests/tools/test_mcp_registration_paths.py`

**Interfaces:**
- Produces: `RegistrationCandidate` using final prefixed `registry_name` for every raw tool and generated utility.
- Produces: `validate_registration_candidates(candidates, ownership_snapshot) -> RegistrationResult`.
- Produces: `commit_registration_candidates(server_name, candidates) -> list[str]`.

- [ ] **Step 1: Write production-path collision tests**

```python
@pytest.mark.parametrize("path", ["eager", "lazy", "refresh"])
def test_registration_path_rejects_raw_utility_collision(path, registration_harness):
    result = registration_harness.register(
        path=path,
        raw_tools=[fake_tool("list_resources")],
        utilities=[fake_resource_utility("list_resources")],
    )
    assert result.registered_names == []
    assert result.registry_snapshot == {}


def test_all_paths_produce_identical_registration_result(registration_harness):
    results = {
        path: registration_harness.register(path=path, raw_tools=collision_fixture())
        for path in ("eager", "lazy", "refresh")
    }
    assert results["eager"].accepted == results["lazy"].accepted == results["refresh"].accepted
    assert results["eager"].rejected == results["lazy"].rejected == results["refresh"].rejected
```

- [ ] **Step 2: Run the tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_mcp_registration_paths.py -q
```

Expected: lazy registration misses raw-versus-utility collisions because raw names and already-prefixed utility names are compared in different namespaces.

- [ ] **Step 3: Introduce one candidate representation**

```python
@dataclass(frozen=True)
class RegistrationCandidate:
    registry_name: str
    raw_name: str
    origin: str
    schema: dict
    handler: Callable
    check_fn: Callable | None
    descriptor: CapabilityDescriptor
```

Both live and cached collectors convert raw tools and utilities to final prefixed `registry_name` before validation. Filtering, description scanning, schema conversion, descriptor creation, and utility generation happen before the complete candidate list is validated.

- [ ] **Step 4: Validate once and commit once**

`validate_registration_candidates()` rejects all candidates sharing a normalized final registry name and all cross-owner collisions. It performs no registry mutation. `commit_registration_candidates()` receives only accepted candidates, holds the registry mutation lock, registers descriptors with handlers, and returns the committed names. Eager and refresh call the live collector; lazy calls the cache collector; all three call the same validator and committer.

- [ ] **Step 5: Preserve refresh atomicity**

Refresh fetches and validates the complete new candidate set before deregistering stale tools. If validation fails, retain the previous registered set and record the error. Once valid, replace the server-owned set under the registry lock so callers cannot observe a partially updated tool list.

- [ ] **Step 6: Verify all three paths**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_mcp_registration_paths.py tests\tools\test_mcp_tool_security.py tests\tools\test_mcp_tool_circuit_breaker.py -q
```

### Task 3: Put Principal Creation at Channel Ingress Only

**Files:**
- Create: `hermes/security/ingress.py`
- Modify: `hermes/security/principal.py`
- Modify: `run_agent.py`
- Modify: `hermes_cli/oneshot.py`
- Modify: `gateway/run.py`
- Modify: `gateway/platforms/api_server.py`
- Modify: `telegram_bot.py`
- Modify: `gui/app.py`
- Modify: `gui/tabs/assistant_tab.py`
- Test: `tests/hermes/test_principal_ingress.py`
- Create: `tests/hermes/test_channel_principal_integration.py`

**Interfaces:**
- Produces: `principal_scope(principal: PrincipalContext)` context manager.
- Produces: local principal factories for CLI, one-shot, and GUI that use configured owner identity and explicit local-admin configuration.
- Consumes: authenticated `ctx.source.user_id`, Telegram `effective_user.id`, and configured single-admin API owner.

- [ ] **Step 1: Write adapter-seam tests**

```python
def test_nested_agent_turn_preserves_gateway_principal(fake_agent_turn):
    principal = PrincipalContext("actor-1", "owner-1", "gateway", "session-1", ())
    result = fake_agent_turn.run_with_bound_principal(principal)
    assert result.observed_principal == principal
    assert current_principal.get() is None


def test_api_without_configured_owner_returns_401(api_adapter, monkeypatch):
    monkeypatch.delenv("HERMES_API_OWNER_USER_ID", raising=False)
    response = api_adapter.invoke_without_owner()
    assert response.status == 401


def test_gui_turn_uses_gui_platform(gui_assistant_harness):
    observed = gui_assistant_harness.run_turn()
    assert observed.platform == "gui"
```

Also cover CLI, one-shot, Telegram missing/effective user, Gateway `ctx.source.user_id`, nested turns, exception cleanup, and two concurrent contexts.

- [ ] **Step 2: Run the tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_channel_principal_integration.py tests\hermes\test_principal_ingress.py -q
```

Expected: GUI is observed as CLI, nested test does not execute a turn, and current API/Gateway seams lack direct test coverage.

- [ ] **Step 3: Add one safe scope primitive**

```python
@contextmanager
def principal_scope(principal: PrincipalContext):
    existing = current_principal.get()
    if existing is not None:
        yield existing
        return
    token = current_principal.set(principal)
    try:
        yield principal
    finally:
        current_principal.reset(token)
```

Reject attempts by a nested channel to replace an existing principal with a different actor/owner. `PrincipalContext.roles` remains empty by default. Only trusted local configuration grants `admin`.

- [ ] **Step 4: Remove identity invention from `AIAgent`**

`AIAgent.run_conversation()` consumes the current principal and never labels an arbitrary caller as CLI. CLI startup binds a local principal before calling the agent. Tests or internal callers that need session-scoped tools must bind a test/server principal explicitly.

- [ ] **Step 5: Bind each channel from its trusted source**

- CLI: `HERMES_CLI_USER_ID` or OS user, platform `cli`; admin only when `HERMES_LOCAL_ADMIN=true`.
- One-shot: same local identity policy, platform `oneshot`.
- Gateway: `ctx.source.user_id`; no `agent.owner_user_id` fallback for user-originated turns.
- API: `HERMES_API_OWNER_USER_ID` for the current single-admin bearer-token model; validate before executor work and raise `web.HTTPUnauthorized` through an aiohttp handler seam.
- Telegram: require `update.effective_user.id`; roles remain empty unless an explicit authorization mapping grants them.
- GUI: `HERMES_GUI_OWNER_USER_ID` or OS local identity, platform `gui`; bind inside the existing worker-thread turn wrapper.

- [ ] **Step 6: Verify channel behavior and context cleanup**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_channel_principal_integration.py tests\hermes\test_principal_ingress.py tests\hermes\test_telegram_authorization.py tests\hermes\test_telegram_product_research_routing.py -q
```

### Task 4: Make Skill Validation Consume the Governed Capability Snapshot

**Files:**
- Modify: `tools/skills_guard.py`
- Modify: `tools/skill_manager_tool.py`
- Modify: governed `skills/*/SKILL.md`
- Modify: `tests/tools/test_skill_contracts.py`

**Interfaces:**
- Consumes: immutable `CapabilityCatalog` snapshot supplied by runtime/bootstrap or test fixture.
- Produces: deterministic validation without importing tools, discovering MCP servers, or mutating the registry.

- [ ] **Step 1: Add snapshot and governance tests**

```python
def test_validator_has_no_discovery_side_effect(monkeypatch, governed_skill, catalog_snapshot):
    monkeypatch.setattr("tools.registry.discover_builtin_tools", lambda: pytest.fail("must not discover"))
    assert validate_bundled_skill_tools(governed_skill, catalog_snapshot) == []


def test_tool_using_skill_must_declare_governance(tool_using_skill, catalog_snapshot):
    errors = validate_bundled_skill_tools(tool_using_skill, catalog_snapshot)
    assert any("governed" in error for error in errors)
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_skill_contracts.py -q
```

- [ ] **Step 3: Validate against descriptors, not names alone**

Change the validator input to a `CapabilityCatalog` or serialized descriptor mapping. Every first-party governed skill declares `metadata.hermes.governed: true`, `allowed-tools`, and `requires_tools`. A documentation-only skill declares `documentation_only: true`. Unknown or absent classification is an error when the body/frontmatter declares tool use. Paid tools require an approval-compatible descriptor.

- [ ] **Step 4: Verify all governed skills**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_skill_contracts.py tests\hermes\test_capability_catalog.py -q
```

### Task 5: Gate A Acceptance and Handoff

**Files:**
- Modify: `docs/architecture-decisions/010-general-purpose-agent-platform.md`
- Modify: `docs/superpowers/plans/2026-08-12-hermes-agent-platform-standardization.md`
- Create: `docs/runbooks/gate-a-verification.md`

**Interfaces:**
- Produces: reproducible verification evidence and a clean boundary before Gate B.

- [ ] **Step 1: Run focused Gate A verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_platform_architecture_contract.py tests\tools\test_mcp_tool_security.py tests\tools\test_mcp_registration_paths.py tests\tools\test_capability_registration.py tests\hermes\test_canonical_runtime.py tests\hermes\test_capability_catalog.py tests\hermes\test_principal_ingress.py tests\hermes\test_channel_principal_integration.py tests\tools\test_skill_contracts.py -q
```

- [ ] **Step 2: Run regressions and compile checks**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_mcp_tool_circuit_breaker.py tests\hermes\test_telegram_authorization.py tests\hermes\test_telegram_product_research_routing.py tests\workers\test_canonical_job_worker.py tests\hermes\test_product_intelligence_integration.py -q
.\.venv\Scripts\python.exe -m compileall -q agent core gateway gui hermes hermes_cli mcp_servers providers server tools workers
git diff --check
```

- [ ] **Step 3: Record known baseline separately**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_p2_routing_ownership.py -q
```

Record the two known routing failures without calling them Gate B work; channel convergence belongs to Task 10/Gate E. Any new failure blocks Gate A.

- [ ] **Step 4: Verify security invariants with executable inventory**

The runbook records commands proving:

- every model-visible production tool has a descriptor;
- no dispatch-time name inference remains;
- eager, lazy, and refresh return identical accepted/rejected names;
- missing principal fails closed for session capabilities;
- external MCP receives no owner unless explicitly contracted;
- no implicit admin or `default_owner` remains;
- every channel binds and clears the expected principal;
- invalid MCP secret allowlists and cross-server secret access are rejected.

- [ ] **Step 5: Review and stop**

Keep ADR-010 at `Proposed`. Do not commit or begin Gate B. Report exact test counts, baseline failures, production descriptor coverage count, diff stat, and remaining risks for reviewer approval.

## Dependency Order

1. Task 1 establishes descriptor ownership and must finish first.
2. Task 2 consumes descriptor creation for MCP candidates.
3. Task 3 can run after Task 1 and may proceed in parallel with Task 2.
4. Task 4 requires the coherent descriptor snapshot from Task 1.
5. Task 5 requires Tasks 1-4.

## Stop Conditions

- Any production tool dispatches using inferred metadata.
- Any MCP path compares raw names while another compares final registry names.
- Registry mutation begins before complete candidate validation.
- A channel creates a fabricated owner or implicit admin role.
- `AIAgent` overwrites an ingress principal.
- GUI runs under platform `cli`.
- A skill validation run starts tool discovery or an MCP process.
- A new regression appears outside the two recorded routing baseline failures.

## Completion Definition

Gate A remediation is complete only when descriptors are present on all model-visible production entries, all MCP paths share one final-name candidate pipeline, every channel integration test executes a real adapter seam, and the full Gate A verification matrix passes without live providers.
