# Hermes Capability Catalog And Domain Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Hermes stable, policy-governed knowledge of native, plugin, and MCP capabilities while exposing tool schemas progressively through domain skills and Tool Search.

**Architecture:** Build a project-owned catalog service over Gate 1 `CapabilityDescriptor` contracts and upstream `ToolRegistry`/MCP discovery. Discovery writes immutable versioned snapshots; policy filters unavailable or unauthorized bindings before Tool Search exposes a schema. Skills describe decision procedure and permitted stable capability IDs without owning network calls or workflow state.

**Tech Stack:** Python 3.10+, upstream ToolRegistry/MCP discovery/skills, SQLite, SHA-256 canonical JSON, pytest, `uv`.

## Global Constraints

- Gate 2 must be accepted before this plan starts.
- Stable capability IDs never depend on MCP server or wire-tool names.
- Missing, unhealthy, unauthorized, or schema-incompatible capabilities fail closed.
- Full tool schemas are loaded lazily; the base Agent Turn receives compact capability summaries.
- Skills are instructions only and cannot call providers, mutate workflow state, or bypass policy.
- `note.create` remains reserved and is not registered.
- Tests use fake registries and fake MCP discovery; no network or paid calls.

---

## File Map

- `hermes_personal/capabilities/manifest.py`: initial stable-ID declarations and expected schemas.
- `hermes_personal/capabilities/bindings.py`: discovered implementation binding records.
- `hermes_personal/capabilities/snapshots.py`: immutable SQLite catalog snapshots.
- `hermes_personal/capabilities/discovery.py`: upstream registry/MCP anti-corruption adapter.
- `hermes_personal/capabilities/policy.py`: owner, workflow, health, schema, risk, and principal checks.
- `hermes_personal/capabilities/search.py`: progressive search and lazy schema loading.
- `hermes_personal/capabilities/service.py`: catalog reload/resolve API.
- `skills/hermes-personal/*/SKILL.md`: product, video, and learning instructions.

### Task 1: Declare The Initial Stable Capability Manifest

**Files:**
- Create: `hermes_personal/capabilities/manifest.py`
- Create: `hermes_personal/capabilities/bindings.py`
- Create: `hermes_personal/capabilities/__init__.py`
- Test: `tests/hermes_personal/capabilities/test_manifest.py`

**Interfaces:**
- Consumes: Gate 1 `CapabilityDescriptor`.
- Produces: `CapabilitySpec`, `ImplementationBinding`, and `INITIAL_CAPABILITIES`.

- [ ] **Step 1: Write the manifest completeness test**

```python
EXPECTED = {
    "product.research", "product.resource_pack.build", "product.resource_pack.lock",
    "video.brief.create", "video.scene_plan.create", "video.storyboard.create",
    "video.render", "video.export", "knowledge.candidate.create", "knowledge.retrieve",
}

def test_initial_manifest_has_exact_cutover_capabilities():
    assert set(INITIAL_CAPABILITIES) == EXPECTED
    assert "note.create" not in INITIAL_CAPABILITIES
    assert all(spec.input_schema_version == "1.0" for spec in INITIAL_CAPABILITIES.values())
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/hermes_personal/capabilities/test_manifest.py -q`

Expected: FAIL on missing package.

- [ ] **Step 3: Implement explicit specs and bindings**

```python
@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    owner: str
    input_schema_version: str
    output_schema_version: str
    allowed_skills: tuple[str, ...]
    allowed_workflows: tuple[str, ...]
    approval_policy: str
    risk: RiskLevel
    cost_class: CostClass

@dataclass(frozen=True)
class ImplementationBinding:
    capability_id: str
    wire_name: str
    source: CapabilitySource
    provider: str
    implementation_version: str
    input_schema_version: str
    output_schema_version: str
    schema_digest: str
    health: HealthStatus
```

Declare all ten manifest entries explicitly. Product resource locking, rendering, export, and knowledge promotion-affecting creation must carry their exact approval policy; no default wildcard skill/workflow permissions are allowed.

Use this policy/risk/cost matrix:

| Capability ID | Approval policy | Risk | Cost |
| --- | --- | --- | --- |
| `product.research` | `none` | `low` | `free` |
| `product.resource_pack.build` | `none` | `medium` | `metered` |
| `product.resource_pack.lock` | `hitl:product_lock` | `high` | `free` |
| `video.brief.create` | `precondition:product_locked` | `medium` | `metered` |
| `video.scene_plan.create` | `precondition:brief_approved` | `medium` | `metered` |
| `video.storyboard.create` | `precondition:scene_approved` | `medium` | `paid` |
| `video.render` | `hitl:storyboard_and_budget` | `high` | `paid` |
| `video.export` | `hitl:final` | `high` | `paid` |
| `knowledge.candidate.create` | `review_required` | `medium` | `free` |
| `knowledge.retrieve` | `approved_only` | `low` | `free` |

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/hermes_personal/capabilities/test_manifest.py -q`

Expected: `1 passed`.

```powershell
git add -- hermes_personal/capabilities tests/hermes_personal/capabilities/test_manifest.py
git commit -m "feat: declare stable hermes capabilities"
```

### Task 2: Persist Immutable Discovery Snapshots

**Files:**
- Create: `hermes_personal/capabilities/snapshots.py`
- Modify: `hermes_personal/storage/sqlite.py`
- Test: `tests/hermes_personal/capabilities/test_snapshots.py`

**Interfaces:**
- Consumes: tuple of `ImplementationBinding` and canonical tool schema JSON.
- Produces: `CapabilitySnapshotRepository.save(bindings) -> CatalogSnapshot` and `latest()`.

- [ ] **Step 1: Write snapshot immutability tests**

```python
def test_equal_discovery_reuses_snapshot(snapshot_repository, binding_factory):
    first = snapshot_repository.save((binding_factory(),))
    second = snapshot_repository.save((binding_factory(),))
    assert first.snapshot_id == second.snapshot_id

def test_changed_wire_binding_creates_new_snapshot(snapshot_repository, binding_factory):
    first = snapshot_repository.save((binding_factory(wire_name="mcp__pi__research"),))
    second = snapshot_repository.save((binding_factory(wire_name="mcp__pi_v2__research"),))
    assert first.snapshot_id != second.snapshot_id
    assert snapshot_repository.get(first.snapshot_id).digest == first.digest
```

- [ ] **Step 2: Verify red, then add snapshot tables**

Run: `uv run pytest tests/hermes_personal/capabilities/test_snapshots.py -q`

Expected: FAIL on missing repository.

Add `capability_snapshot(snapshot_id, digest UNIQUE, created_at)` and `capability_snapshot_binding(snapshot_id, capability_id, binding_json, PRIMARY KEY(snapshot_id, capability_id))`. Compute digest as SHA-256 over UTF-8 canonical JSON using sorted keys and compact separators. Never update rows in an existing snapshot.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/capabilities/test_snapshots.py -q`

Expected: `2 passed`.

```powershell
git add -- hermes_personal/storage/sqlite.py hermes_personal/capabilities/snapshots.py tests/hermes_personal/capabilities/test_snapshots.py
git commit -m "feat: persist capability catalog snapshots"
```

### Task 3: Discover And Validate Upstream Tool Bindings

**Files:**
- Create: `hermes_personal/capabilities/discovery.py`
- Test: `tests/hermes_personal/capabilities/test_discovery.py`

**Interfaces:**
- Consumes: `ToolRegistry.get_definitions()`, `discover_mcp_tools()`, and an explicit wire-name mapping.
- Produces: `CapabilityDiscovery.scan() -> DiscoveryResult`.

- [ ] **Step 1: Write fake-registry discovery tests**

```python
def test_discovery_binds_wire_tool_to_stable_id(fake_registry, discovery):
    fake_registry.add("mcp__product_intelligence__research_product", input_schema={"type": "object"})
    result = discovery.scan()
    binding = result.by_capability_id["product.research"]
    assert binding.wire_name == "mcp__product_intelligence__research_product"
    assert binding.health == "healthy"

def test_schema_mismatch_is_unavailable(fake_registry, discovery):
    fake_registry.add("mcp__video_factory__render", input_schema={"type": "string"})
    result = discovery.scan()
    assert result.by_capability_id["video.render"].health == "unavailable"
    assert result.diagnostics["video.render"].code == "schema_incompatible"
```

- [ ] **Step 2: Verify red and implement the anti-corruption adapter**

Run: `uv run pytest tests/hermes_personal/capabilities/test_discovery.py -q`

Expected: FAIL on missing discovery.

Define `WireBindingRule(capability_id, accepted_wire_names, provider, source)` for every manifest entry. Discovery must call upstream APIs through injected callables, hash normalized JSON schemas, reject duplicate wire ownership, mark absent tools unavailable, and return diagnostics without throwing away the last persisted healthy snapshot.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/capabilities/test_discovery.py -q`

Expected: `2 passed`.

```powershell
git add -- hermes_personal/capabilities/discovery.py tests/hermes_personal/capabilities/test_discovery.py
git commit -m "feat: discover stable upstream capability bindings"
```

### Task 4: Enforce Capability Policy Before Model Exposure

**Files:**
- Create: `hermes_personal/capabilities/policy.py`
- Create: `hermes_personal/capabilities/service.py`
- Test: `tests/hermes_personal/capabilities/test_policy.py`

**Interfaces:**
- Consumes: principal, skill ID, workflow state, catalog snapshot, and budget authorization summary.
- Produces: `CapabilityDecision(allowed, code, descriptor)` and fail-closed resolution.

- [ ] **Step 1: Write policy matrix tests**

```python
@pytest.mark.parametrize("health", ["unknown", "degraded", "unavailable"])
def test_non_healthy_binding_is_hidden(policy, context_factory, descriptor_factory, health):
    decision = policy.evaluate(context_factory(), descriptor_factory(health=health))
    assert decision.allowed is False
    assert decision.code == f"capability_{health}"

def test_wrong_skill_or_workflow_is_hidden(policy, context_factory, descriptor_factory):
    descriptor = descriptor_factory(allowed_skills=("product-research",), allowed_workflows=("product_research",))
    assert not policy.evaluate(context_factory(skill_id="video-production"), descriptor).allowed
    assert not policy.evaluate(context_factory(workflow_type="knowledge_learning"), descriptor).allowed
```

- [ ] **Step 2: Verify red, implement exact evaluation order, verify green**

Run: `uv run pytest tests/hermes_personal/capabilities/test_policy.py -q`

Expected before implementation: FAIL. Evaluate in this order: descriptor exists, health is `healthy`, schema versions match manifest, principal is authorized, skill is allowed, workflow transition is allowed, approval precondition is satisfied, budget envelope permits exposure. Return a machine-readable denial code and never expose the wire name on authorization failure.

Run again; expected: all parameterized cases pass.

- [ ] **Step 3: Commit**

```powershell
git add -- hermes_personal/capabilities/policy.py hermes_personal/capabilities/service.py tests/hermes_personal/capabilities/test_policy.py
git commit -m "feat: enforce capability exposure policy"
```

### Task 5: Add Progressive Tool Search And Lazy Schemas

**Files:**
- Create: `hermes_personal/capabilities/search.py`
- Test: `tests/hermes_personal/capabilities/test_search.py`

**Interfaces:**
- Consumes: compact query, policy context, catalog service, and upstream schema loader.
- Produces: `search(query, context, limit=5) -> tuple[CapabilitySummary, ...]` and `load_schema(capability_id, context) -> Mapping[str, Any]`.

- [ ] **Step 1: Write search disclosure tests**

```python
def test_search_returns_summary_without_full_schema(search_service, context):
    result = search_service.search("nghien cuu san pham", context)
    assert result[0].capability_id == "product.research"
    assert not hasattr(result[0], "input_schema")

def test_schema_is_loaded_only_after_policy_allows(search_service, denied_context, schema_loader):
    with pytest.raises(CapabilityUnavailable):
        search_service.load_schema("video.render", denied_context)
    assert schema_loader.calls == []
```

- [ ] **Step 2: Verify red and implement deterministic ranking**

Run: `uv run pytest tests/hermes_personal/capabilities/test_search.py -q`

Expected: FAIL on missing search service.

Rank only allowed healthy capabilities using normalized token overlap across stable ID, description, skill tags, and workflow tags; use stable ID as tie-breaker. `load_schema` resolves policy again, loads the current wire schema, verifies its digest against the active snapshot, and raises `SchemaChanged` before exposure when it differs.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/capabilities/test_search.py -q`

Expected: `2 passed`.

```powershell
git add -- hermes_personal/capabilities/search.py tests/hermes_personal/capabilities/test_search.py
git commit -m "feat: add progressive capability search"
```

### Task 6: Publish Governed Domain Skills

**Files:**
- Create: `skills/hermes-personal/product-research/SKILL.md`
- Create: `skills/hermes-personal/product-video-production/SKILL.md`
- Create: `skills/hermes-personal/knowledge-learning/SKILL.md`
- Test: `tests/hermes_personal/capabilities/test_domain_skills.py`

**Interfaces:**
- Consumes: stable capability IDs and first-class workflow IDs.
- Produces: upstream-loadable progressive instructions.

- [ ] **Step 1: Write skill contract tests**

Load each `SKILL.md` through upstream skill utilities and assert valid frontmatter, unique skill name, explicit `allowed-capabilities`, explicit `allowed-workflows`, clarification conditions, and absence of MCP wire names, shell commands, provider credentials, direct HTTP, or `note.create`.

- [ ] **Step 2: Create the three skills**

`product-research` must ask when product category, platform, market, or budget changes the result and may use only `product.research`, `product.resource_pack.build`, and `knowledge.retrieve`. `product-video-production` must describe the approved state sequence and may use product lock plus video draft/render/export capabilities only through `product_to_video`. `knowledge-learning` may retrieve approved knowledge and create a review candidate; it must never self-approve.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/capabilities/test_domain_skills.py -q`

Expected: all three skills load and all policy assertions pass.

```powershell
git add -- skills/hermes-personal tests/hermes_personal/capabilities/test_domain_skills.py
git commit -m "feat: add governed hermes domain skills"
```

### Task 7: Lock Reload, Outage, And Compatibility Behavior

**Files:**
- Create: `tests/hermes_personal/capabilities/test_catalog_acceptance.py`
- Create: `docs/hermes-personal/capabilities.md`

**Interfaces:**
- Consumes: discovery, snapshots, policy, search, and skills.
- Produces: Gate 3 acceptance evidence and operational reload contract.

- [ ] **Step 1: Add acceptance scenarios**

Cover startup snapshot creation, controlled reload with one changed wire binding, old snapshot readability, current binding resolution by stable ID, MCP outage using last snapshot only for diagnostics while exposure fails closed, schema drift rejection, unauthorized principal rejection, and actionable event codes returned to Agent Turn.

- [ ] **Step 2: Document controlled reload**

Document one flow: pause model exposure, discover, validate all mandatory bindings, persist immutable snapshot, atomically activate it, emit `capability_catalog_reloaded`, then resume exposure. On failure retain the previous active snapshot identifier but mark affected live health unavailable.

- [ ] **Step 3: Run Gate 3 verification and commit**

```powershell
uv run pytest tests/hermes_personal/capabilities tests/hermes_personal/test_upstream_compatibility.py tests/tools/test_registry.py tests/tools/test_mcp_capability_gating.py -q
git diff --check
git add -- tests/hermes_personal/capabilities/test_catalog_acceptance.py docs/hermes-personal/capabilities.md
git commit -m "test: lock capability catalog behavior"
```

Expected: pytest exits `0`; `git diff --check` prints nothing.

## Gate 3 Exit Criteria

- Exactly ten initial stable capability IDs are registered; `note.create` is absent.
- Provider and wire-name changes do not alter workflow/skill contracts.
- Startup and controlled reload create immutable, digest-verified snapshots.
- Policy hides missing, unhealthy, unauthorized, incompatible, or disallowed tools.
- Tool Search exposes compact summaries first and full schemas only after policy and digest checks.
- Domain skills load through upstream skill utilities and contain no provider execution logic.
- MCP outage and schema drift return actionable failures without fake success.
