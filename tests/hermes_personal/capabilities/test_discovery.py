from __future__ import annotations

import re
from typing import Any

import pytest

from hermes_personal.capabilities.discovery import (
    DEFAULT_WIRE_BINDING_RULES,
    CapabilityDiscovery,
    WireBindingRule,
)
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.capabilities.snapshots import CapabilitySnapshotRepository
from hermes_personal.storage.sqlite import connect
from tools.registry import ToolRegistry


class FakeToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self._toolsets: dict[str, str] = {}
        self._failing_checks: set[str] = set()
        self._raw_schemas: dict[str, dict[str, Any]] = {}
        self._malformed_defs: dict[str, Any] = {}
        self.probed_tools: list[str] = []

    def register_fake(
        self,
        name: str,
        toolset: str,
        schema: dict[str, Any] | None = None,
        check_fn_pass: bool = True,
        malformed_envelope: Any | None = None,
    ) -> None:
        schema_dict = schema if schema is not None else {
            "description": f"Fake tool {name}",
            "parameters": {"type": "object", "properties": {}},
        }
        self._tools[name] = schema_dict
        self._toolsets[name] = toolset
        self._raw_schemas[name] = schema_dict
        if malformed_envelope is not None:
            self._malformed_defs[name] = malformed_envelope
        if not check_fn_pass:
            self._failing_checks.add(name)

    def get_all_tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def get_definitions(
        self, tool_names: set[str], quiet: bool = False
    ) -> list[dict[str, Any]]:
        self.probed_tools.extend(sorted(tool_names))
        result = []
        for name in sorted(tool_names):
            if name in self._tools and name not in self._failing_checks:
                if name in self._malformed_defs:
                    result.append(self._malformed_defs[name])
                else:
                    schema = self._tools[name]
                    schema_with_name = {**schema, "name": name}
                    result.append({"type": "function", "function": schema_with_name})
        return result

    def get_schema(self, name: str) -> dict[str, Any] | None:
        return self._raw_schemas.get(name)

    def get_toolset_for_tool(self, name: str) -> str | None:
        return self._toolsets.get(name)


def _populate_full_fake_registry(registry: FakeToolRegistry) -> None:
    wire_map = {
        "product.research": ("mcp__product_intelligence__research_product", "product_intelligence"),
        "product.resource_pack.build": ("mcp__product_intelligence__build_resource_pack", "product_intelligence"),
        "product.resource_pack.lock": ("mcp__product_intelligence__lock_resource_pack", "product_intelligence"),
        "video.brief.create": ("mcp__video_factory__create_brief", "video_factory"),
        "video.scene_plan.create": ("mcp__video_factory__create_scene_plan", "video_factory"),
        "video.storyboard.create": ("mcp__video_factory__create_storyboard", "video_factory"),
        "video.render": ("mcp__video_factory__render", "video_factory"),
        "video.export": ("mcp__video_factory__export", "video_factory"),
        "knowledge.candidate.create": ("mcp__learning__create_candidate", "learning"),
        "knowledge.retrieve": ("mcp__learning__retrieve", "learning"),
    }
    for _, (wire_name, toolset) in wire_map.items():
        registry.register_fake(wire_name, toolset)


SHA256_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


def test_successful_full_discovery():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    assert len(result.bindings) == 10
    assert len(result.diagnostics) == 0
    assert all(b.health == "healthy" for b in result.bindings)

    res_binding = result.by_capability_id["product.research"]
    assert res_binding.wire_name == "mcp__product_intelligence__research_product"
    assert res_binding.provider == "product_intelligence"
    assert SHA256_PATTERN.match(res_binding.schema_digest)


def test_candidate_only_probing():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)
    registry.register_fake("unrelated_expensive_tool", "unrelated")

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    assert "unrelated_expensive_tool" not in registry.probed_tools
    assert len(result.bindings) == 10


def test_missing_tool_produces_unavailable_binding_and_diagnostic():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)
    registry._tools.pop("mcp__video_factory__render")

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    assert len(result.bindings) == 10
    render_binding = result.by_capability_id["video.render"]
    assert render_binding.health == "unavailable"
    assert SHA256_PATTERN.match(render_binding.schema_digest)

    diags = [d for d in result.diagnostics if d.capability_id == "video.render"]
    assert len(diags) == 1
    assert diags[0].code == "tool_not_found"


def test_failing_check_fn_produces_unavailable_binding():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)
    registry.register_fake(
        "mcp__video_factory__export",
        "video_factory",
        check_fn_pass=False,
    )

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    export_binding = result.by_capability_id["video.export"]
    assert export_binding.health == "unavailable"
    assert SHA256_PATTERN.match(export_binding.schema_digest)

    diags = [d for d in result.diagnostics if d.capability_id == "video.export"]
    assert len(diags) == 1
    assert diags[0].code == "check_failed"


def test_schema_incompatibility_detected():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)
    registry.register_fake(
        "mcp__learning__retrieve",
        "learning",
        schema={"description": "Invalid schema", "parameters": 12345},  # type: ignore[dict-item]
    )

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    retrieve_binding = result.by_capability_id["knowledge.retrieve"]
    assert retrieve_binding.health == "unavailable"
    assert SHA256_PATTERN.match(retrieve_binding.schema_digest)

    diags = [d for d in result.diagnostics if d.capability_id == "knowledge.retrieve"]
    assert len(diags) == 1
    assert diags[0].code == "schema_incompatible"


def test_malformed_definition_envelope_produces_schema_incompatible():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)
    registry.register_fake(
        "mcp__video_factory__render",
        "video_factory",
        malformed_envelope={"type": "function", "function": "not_a_dict"},
    )

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    render_binding = result.by_capability_id["video.render"]
    assert render_binding.health == "unavailable"
    assert SHA256_PATTERN.match(render_binding.schema_digest)

    diags = [d for d in result.diagnostics if d.capability_id == "video.render"]
    assert len(diags) == 1
    assert diags[0].code == "schema_incompatible"


def test_ambiguous_wire_mapping_detected():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)
    registry.register_fake("product_intelligence_research", "product_intelligence")

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    res_binding = result.by_capability_id["product.research"]
    assert res_binding.health == "unavailable"
    assert SHA256_PATTERN.match(res_binding.schema_digest)

    diags = [d for d in result.diagnostics if d.capability_id == "product.research"]
    assert len(diags) == 1
    assert diags[0].code == "ambiguous_wire_mapping"


def test_duplicate_wire_ownership_detected():
    registry = FakeToolRegistry()

    # Complete 10-rule fixture with two capabilities claiming the same wire tool name
    custom_rules = list(DEFAULT_WIRE_BINDING_RULES)
    custom_rules[1] = WireBindingRule(
        capability_id="product.resource_pack.build",
        accepted_wire_names=("mcp__product_intelligence__research_product",),
        provider="product_intelligence",
    )

    registry.register_fake(
        "mcp__product_intelligence__research_product", "product_intelligence"
    )
    _populate_full_fake_registry(registry)

    discovery = CapabilityDiscovery(rules=custom_rules)
    result = discovery.scan(registry)

    assert result.by_capability_id["product.research"].health == "unavailable"
    assert result.by_capability_id["product.resource_pack.build"].health == "unavailable"
    assert SHA256_PATTERN.match(result.by_capability_id["product.research"].schema_digest)

    diags = [d for d in result.diagnostics if d.code == "duplicate_wire_ownership"]
    assert len(diags) == 2


def test_rule_configuration_validation():
    # Duplicate rule for capability_id
    dup_rules = list(DEFAULT_WIRE_BINDING_RULES)
    dup_rules.append(DEFAULT_WIRE_BINDING_RULES[0])
    with pytest.raises(
        ValueError, match="duplicate WireBindingRule for capability_id: product.research"
    ):
        CapabilityDiscovery(rules=dup_rules)

    # Missing manifest capabilities
    incomplete_rules = [DEFAULT_WIRE_BINDING_RULES[0]]
    with pytest.raises(
        ValueError, match="missing WireBindingRule for manifest capabilities"
    ):
        CapabilityDiscovery(rules=incomplete_rules)

    # Duplicate accepted wire names in single rule
    with pytest.raises(
        ValueError, match="duplicate accepted_wire_names in rule for capability_id"
    ):
        WireBindingRule(
            capability_id="product.research",
            accepted_wire_names=("same_wire", "same_wire"),
            provider="product_intelligence",
        )


def test_non_json_serializable_schema_isolation():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)

    registry.register_fake(
        "mcp__video_factory__render",
        "video_factory",
        schema={"description": "Corrupt", "parameters": {"bad_set": {1, 2, 3}}},
    )

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    render_binding = result.by_capability_id["video.render"]
    assert render_binding.health == "unavailable"
    assert SHA256_PATTERN.match(render_binding.schema_digest)

    diags = [d for d in result.diagnostics if d.capability_id == "video.render"]
    assert len(diags) == 1
    assert diags[0].code == "schema_incompatible"

    # Other capabilities remain unaffected and healthy
    assert result.by_capability_id["product.research"].health == "healthy"


def test_discovery_result_can_be_saved_to_snapshot_repository(tmp_path):
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)

    discovery = CapabilityDiscovery()
    disc_result = discovery.scan(registry)

    db_path = tmp_path / "test_discovery_snapshot.db"
    conn = connect(db_path)
    snapshot_repo = CapabilitySnapshotRepository(conn)

    snapshot = snapshot_repo.save_and_activate(disc_result.bindings)
    assert snapshot is not None
    assert snapshot_repo.get_active().snapshot_id == snapshot.snapshot_id


def test_real_upstream_tool_registry_integration():
    real_registry = ToolRegistry()

    check_probed = False

    def dummy_check():
        nonlocal check_probed
        check_probed = True
        return True

    real_registry.register(
        name="mcp__product_intelligence__research_product",
        toolset="product_intelligence",
        schema={"description": "Real research tool", "parameters": {"type": "object"}},
        handler=lambda **kw: "ok",
        check_fn=dummy_check,
    )

    unrelated_probed = False

    def unrelated_check():
        nonlocal unrelated_probed
        unrelated_probed = True
        return True

    real_registry.register(
        name="unrelated_tool",
        toolset="unrelated",
        schema={"description": "Unrelated", "parameters": {"type": "object"}},
        handler=lambda **kw: "ok",
        check_fn=unrelated_check,
    )

    discovery = CapabilityDiscovery()
    result = discovery.scan(real_registry)

    assert check_probed is True
    assert unrelated_probed is False

    res_binding = result.by_capability_id["product.research"]
    assert res_binding.health == "healthy"
    assert res_binding.wire_name == "mcp__product_intelligence__research_product"
    assert res_binding.provider == "product_intelligence"
    assert SHA256_PATTERN.match(res_binding.schema_digest)

    render_binding = result.by_capability_id["video.render"]
    assert render_binding.health == "unavailable"
    assert SHA256_PATTERN.match(render_binding.schema_digest)
