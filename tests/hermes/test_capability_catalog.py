import pytest
from hermes.capabilities.models import CapabilityDescriptor
from hermes.capabilities.catalog import CapabilityCatalog, CapabilityEntry


def fake_entry(wire_name: str, toolset: str = "default") -> CapabilityEntry:
    return CapabilityEntry(
        wire_name=wire_name,
        toolset=toolset,
        description=f"Test tool {wire_name}",
    )


def test_catalog_distinguishes_external_and_first_party_mcp():
    catalog = CapabilityCatalog.from_entries([
        fake_entry("mcp__hermes_video__video_analyze", toolset="mcp-hermes_video"),
        fake_entry("mcp__product_intelligence__research_product", toolset="mcp-product_intelligence"),
    ], managed_servers={"hermes_video"})

    desc_vf = catalog.require("mcp__hermes_video__video_analyze")
    assert desc_vf.source == "hermes_mcp"
    assert desc_vf.trust == "first_party"

    desc_pi = catalog.require("mcp__product_intelligence__research_product")
    assert desc_pi.source == "external_mcp"
    assert desc_pi.trust == "configured_external"


def test_capability_catalog_snapshot_consistency_and_fail_closed():
    from hermes.tools.registry import registry
    catalog = CapabilityCatalog.from_registry_snapshot(registry._tools)

    with pytest.raises(KeyError):
        catalog.require("non_existent_tool_capability_xyz")

    assert catalog.get("non_existent_tool_capability_xyz") is None


def test_catalog_uses_registration_provenance():
    entry = CapabilityEntry(
        wire_name="mcp__custom__tool",
        toolset="mcp-custom",
        provenance="hermes_mcp",
        principal_mode="session",
    )
    catalog = CapabilityCatalog.from_entries([entry])
    desc = catalog.require("mcp__custom__tool")
    assert desc.source == "hermes_mcp"
    assert desc.trust == "first_party"


def test_catalog_does_not_infer_side_effects_from_name():
    entry = CapabilityEntry(
        wire_name="get_and_delete_user_data",
        side_effects="paid",
    )
    catalog = CapabilityCatalog.from_entries([entry])
    desc = catalog.require("get_and_delete_user_data")
    assert desc.side_effects == "paid"


def test_registry_snapshot_and_catalog_are_consistent():
    from hermes.tools.registry import registry
    registry.register(
        name="test_consistent_tool",
        toolset="test",
        schema={"name": "test_consistent_tool"},
        handler=lambda args: "ok",
    )
    catalog = CapabilityCatalog.from_registry_snapshot(registry._tools)
    desc = catalog.require("test_consistent_tool")
    assert desc.wire_name == "test_consistent_tool"


def test_conflicting_descriptor_registration_is_rejected():
    catalog = CapabilityCatalog()
    desc1 = CapabilityDescriptor(
        capability_id="cap1", wire_name="t1", owner="o1", source="native",
        trust="first_party", version="1.0", toolset="default", side_effects="read",
        principal_mode="session", idempotency="supported", approval_policy="default",
        data_classification="internal"
    )
    desc2 = CapabilityDescriptor(
        capability_id="cap2", wire_name="t1", owner="o2", source="native",
        trust="first_party", version="1.0", toolset="default", side_effects="write",
        principal_mode="none", idempotency="supported", approval_policy="default",
        data_classification="internal"
    )
    catalog.register_descriptor(desc1)
    with pytest.raises(ValueError):
        catalog.register_descriptor(desc2)
