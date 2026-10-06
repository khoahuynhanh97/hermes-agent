# Hermes Capability Catalog And Domain Skills Implementation Plan (Corrected)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Hermes stable, policy-governed knowledge of native, plugin, and MCP capabilities while exposing tool schemas progressively through domain skills, upstream Tool Search integration, active snapshot pointers, and end-to-end turn execution.

**Architecture:** Build a project-owned capability catalog service over Gate 1 `CapabilityDescriptor` contracts, upstream `ToolRegistry` APIs (`get_all_tool_names()`, `get_definitions()`, `get_schema()`), and upstream `tools/tool_search.py`. Discovery writes immutable versioned snapshots and updates a singleton `capability_catalog_state` active pointer; policy filters unavailable, unauthorized, or incompatible capabilities before exposure; domain skills placed under `.agents/skills/hermes-personal-*/` declare permitted capabilities and upstream tool bindings; runtime turn execution integrates capability governance without breaking `AIAgent` signatures or 4-ingress convergence.

**Tech Stack:** Python 3.10+, upstream ToolRegistry/MCP discovery/skills/tool_search, SQLite, SHA-256 canonical JSON, pytest, `uv`.

## Global Constraints

- Gate 2 must be accepted before this plan starts. (Accepted at commit `1efe9c6909`).
- Stable capability IDs never depend on MCP server or wire-tool names.
- Missing, unhealthy, unauthorized, or schema-incompatible capabilities fail closed with structured `CapabilityError`.
- Full tool schemas are loaded lazily; base Agent Turn receives compact capability summaries via upstream `tools/tool_search.py`.
- Active catalog state uses a singleton table (`capability_catalog_state`) with explicit snapshot pointer activation.
- Domain skills reside under `.agents/skills/hermes-personal-*/` declaring both `allowed-capabilities` and upstream `allowed-tools`.
- `note.create` remains reserved and is not registered.
- Public `AIAgent.run_conversation` call signature remains intact; governance integrates through capability adapters.
- Four ingress channels (Telegram, CLI, Web, Omni Chat) converge to canonical turn execution.
- Tests use fake registries and fake MCP discovery; zero network or paid API calls.

---

## File Map

- `hermes_personal/capabilities/__init__.py`: package exports.
- `hermes_personal/capabilities/manifest.py`: initial stable-ID declarations and expected specs.
- `hermes_personal/capabilities/bindings.py`: discovered implementation binding records.
- `hermes_personal/capabilities/snapshots.py`: immutable SQLite catalog snapshots and singleton active state pointer.
- `hermes_personal/capabilities/discovery.py`: upstream `ToolRegistry` and MCP anti-corruption discovery adapter.
- `hermes_personal/capabilities/errors.py`: structured `CapabilityError` definitions.
- `hermes_personal/capabilities/policy.py`: personal assistant policy rules (degraded read allowed, write/paid protected).
- `hermes_personal/capabilities/search.py`: policy adapter over upstream `tools/tool_search.py`.
- `hermes_personal/capabilities/service.py`: catalog lifecycle, reload, and resolution API.
- `.agents/skills/hermes-personal-*/SKILL.md`: governed domain skills for product research, video production, and learning.
- `tests/hermes_personal/capabilities/`: unit, integration, and E2E acceptance tests.

---

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

- [ ] **Step 2: Implement explicit specs, bindings, and manifest**

Declare all ten manifest entries explicitly with schema versions, ownership, risk, cost, approval, skill, and workflow metadata.

---

### Task 2: Persist Immutable Discovery Snapshots And Active Pointer

**Files:**
- Create: `hermes_personal/capabilities/snapshots.py`
- Modify: `hermes_personal/storage/sqlite.py`
- Test: `tests/hermes_personal/capabilities/test_snapshots.py`

---

### Task 3: Discover Upstream Tool Bindings via Official Registry APIs

**Files:**
- Create: `hermes_personal/capabilities/discovery.py`
- Test: `tests/hermes_personal/capabilities/test_discovery.py`

---

### Task 4: Enforce Personal Assistant Capability Policy & Structured Errors

**Files:**
- Create: `hermes_personal/capabilities/errors.py`
- Create: `hermes_personal/capabilities/policy.py`
- Test: `tests/hermes_personal/capabilities/test_policy.py`

---

### Task 5: Adapt Upstream Tool Search And Lazy Schemas

**Files:**
- Create: `hermes_personal/capabilities/search.py`
- Test: `tests/hermes_personal/capabilities/test_search.py`

---

### Task 6: Publish Governed Domain Skills under `.agents/skills/`

**Files:**
- Create: `.agents/skills/hermes-personal-product-research/SKILL.md`
- Create: `.agents/skills/hermes-personal-product-video-production/SKILL.md`
- Create: `.agents/skills/hermes-personal-knowledge-learning/SKILL.md`
- Test: `tests/hermes_personal/capabilities/test_domain_skills.py`

---

### Task 7: Catalog Service, Controlled Reload & Turn Service Integration

**Files:**
- Create: `hermes_personal/capabilities/service.py`
- Modify: `hermes_personal/orchestration/turn_service.py`
- Modify: `hermes_personal/orchestration/upstream_agent.py`

---

### Task 8: End-to-End Acceptance Test & Operational Documentation

**Files:**
- Create: `tests/hermes_personal/capabilities/test_catalog_acceptance.py`
- Create: `docs/hermes-personal/capabilities.md`

---

## Gate 3 Exit Criteria

- Exactly ten initial stable capability IDs are registered; `note.create` is absent.
- `capability_catalog_state` singleton table points to active snapshot atomically.
- ToolRegistry API calls use `get_all_tool_names()`, `get_definitions()`, and `get_schema()`.
- Upstream `tools/tool_search.py` is adapted with policy governance.
- Domain skills reside under `.agents/skills/hermes-personal-*/` specifying `allowed-tools` and `allowed-capabilities`.
- `CapabilityError` provides machine-readable error codes in failed turn events across all 4 ingress channels.
- Personal Assistant Policy allows degraded low-risk/read capabilities best-effort.
- E2E acceptance test verifies full turn execution from ingress request to MCP tool execution.
