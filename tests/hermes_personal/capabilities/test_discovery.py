from __future__ import annotations

import re
from typing import Any

import pytest

from hermes_personal.capabilities.discovery import (
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
        self.probed_tools: list[str] = []

    def register_fake(
        self,
        name: str,
        toolset: str,
        schema: dict[str, Any] | None = None,
        check_fn_pass: bool = True,
    ) -> None:
        schema_dict = schema if schema is not None else {
            "description": f"Fake tool {name}",
            "parameters": {"type": "object", "properties": {}},
        }
        self._tools[name] = schema_dict
        self._toolsets[name] = toolset
        self._raw_schemas[name] = schema_dict
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
    assert re.match(r"^sha256:[a-f0-9]{64}$", res_binding.schema_digest)


def test_candidate_only_probing():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)
    # Register an unrelated tool
    registry.register_fake("unrelated_expensive_tool", "unrelated")

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    assert "unrelated_expensive_tool" not in registry.probed_tools
    assert len(result.bindings) == 10


def test_rule_configuration_validation():
    # Duplicate rule for product.research
    dup_rules = [
        WireBindingRule("product.research", ("w1",), "p1"),
        WireBindingRule("product.research", ("w2",), "p2"),
    ]
    with pytest.raises(ValueError, match="duplicate WireBindingRule for capability_id: product.research"):
        CapabilityDiscovery(rules=dup_rules)

    # Rule missing required manifest capabilities
    incomplete_rules = [
        WireBindingRule("product.research", ("w1",), "p1"),
    ]
    with pytest.raises(ValueError, match="missing WireBindingRule for manifest capabilities"):
        CapabilityDiscovery(rules=incomplete_rules)


def test_non_json_serializable_schema_isolation():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)

    # Corrupt schema with non-serializable set()
    registry.register_fake(
        "mcp__video_factory__render",
        "video_factory",
        schema={"description": "Corrupt", "parameters": {"bad_set": {1, 2, 3}}},
    )

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    render_binding = result.by_capability_id["video.render"]
    assert render_binding.health == "unavailable"
    assert re.match(r"^sha256:[a-f0-9]{64}$", render_binding.schema_digest)

    diags = [d for d in result.diagnostics if d.capability_id == "video.render"]
    assert len(diags) == 1
    assert diags[0].code == "schema_incompatible"

    # Other tools remain healthy
    assert result.by_capability_id["product.research"].health == "healthy"


def test_missing_tool_sentinel_digest_format():
    registry = FakeToolRegistry()
    _populate_full_fake_registry(registry)
    registry._tools.pop("mcp__video_factory__render")

    discovery = CapabilityDiscovery()
    result = discovery.scan(registry)

    render_binding = result.by_capability_id["video.render"]
    assert render_binding.health == "unavailable"
    assert re.match(r"^sha256:[a-f0-9]{64}$", render_binding.schema_digest)


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

    # Register an unrelated tool whose check_fn must NOT be probed
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
    assert re.match(r"^sha256:[a-f0-9]{64}$", res_binding.schema_digest)

    # Missing tools produce unavailable bindings with valid SHA-256 digests
    render_binding = result.by_capability_id["video.render"]
    assert render_binding.health == "unavailable"
    assert re.match(r"^sha256:[a-f0-9]{64}$", render_binding.schema_digest)
