import pytest
from hermes.capabilities.models import CapabilityDescriptor
from hermes.tools.registry import ToolRegistry, discover_builtin_tools

@pytest.fixture
def registry():
    return ToolRegistry()

@pytest.fixture
def read_descriptor():
    return CapabilityDescriptor(
        capability_id="cap_read",
        wire_name="read_probe",
        owner="test",
        source="native",
        trust="first_party",
        version="1.0",
        toolset="test",
        side_effects="read",
        principal_mode="none",
        idempotency="supported",
        approval_policy="default",
        data_classification="internal"
    )

@pytest.fixture
def discovered_registry():
    r = ToolRegistry()
    for mod_name in discover_builtin_tools():
        __import__(mod_name)
    # discover_builtin_tools imports modules which register to the global registry
    # We need to copy from global registry
    from hermes.tools.registry import registry as global_registry
    r._tools = global_registry._tools.copy()
    return r


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
        entry.name for entry in discovered_registry._snapshot_entries()
        if entry.descriptor is None
    ]
    assert missing == []
