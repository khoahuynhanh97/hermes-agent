import pytest

from hermes_personal.contracts import CapabilityCatalog, CapabilityDescriptor


def descriptor(wire_name: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id="product.research",
        wire_name=wire_name,
        owner="product_intelligence",
        source="external_mcp",
        trust="configured_external",
        version="1.0.0",
        toolset="product-intelligence",
        side_effects="external",
        principal_mode="session",
        idempotency="supported",
        approval_policy="none",
        data_classification="internal",
        input_schema_version="1.0",
        output_schema_version="1.0",
        risk="low",
        cost_class="free",
        provider_policy="product-intelligence-default",
        health="healthy",
        allowed_skills=("product-research",),
        allowed_workflows=("product_research", "product_to_video"),
    )


def test_catalog_resolves_stable_id_and_current_wire_name():
    catalog = CapabilityCatalog()
    item = descriptor("mcp__product_intelligence__research_product")
    catalog.register(item)

    assert catalog.resolve("product.research") is item
    assert catalog.resolve("mcp__product_intelligence__research_product") is item


def test_wire_binding_can_change_without_changing_capability_id():
    catalog = CapabilityCatalog()
    catalog.register(descriptor("mcp__pi__research_product"))

    rebound = catalog.rebind_wire(
        "product.research", "mcp__product_intelligence_v2__research"
    )

    assert rebound.capability_id == "product.research"
    assert catalog.resolve("mcp__product_intelligence_v2__research") is rebound
    with pytest.raises(KeyError):
        catalog.resolve("mcp__pi__research_product")


def test_catalog_rejects_two_capabilities_bound_to_one_wire_name():
    catalog = CapabilityCatalog()
    catalog.register(descriptor("mcp__pi__research"))
    conflict = CapabilityDescriptor(
        **{
            **descriptor("mcp__pi__research").__dict__,
            "capability_id": "product.resource_pack.build",
        }
    )

    with pytest.raises(ValueError, match="wire name"):
        catalog.register(conflict)
