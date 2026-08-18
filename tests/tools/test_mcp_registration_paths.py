import pytest
import asyncio
from typing import List, Dict
from unittest.mock import MagicMock

from hermes.tools.mcp_tool import (
    _register_server_tools,
    _register_from_cache_sync,
    MCPServerTask,
    RegistrationCandidate,
    validate_registration_candidates,
    _mcp_tool_server_names,
    _lock as mcp_lock,
)
from hermes.tools.registry import (
    ToolRegistry,
    BatchRegistrationCandidate,
    BatchCommitError,
    RegistrationConflictError,
)
from hermes.capabilities.models import CapabilityDescriptor


class FakeMCPTool:
    def __init__(self, name: str, description: str = "Fake tool"):
        self.name = name
        self.description = description
        self.inputSchema = {"type": "object", "properties": {}}

def fake_tool(name: str) -> FakeMCPTool:
    return FakeMCPTool(name)

def fake_resource_utility(name: str) -> FakeMCPTool:
    return FakeMCPTool(name)

def make_descriptor(wire_name: str, toolset: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=f"cap_{wire_name}",
        wire_name=wire_name,
        owner="test_server",
        source="external_mcp",
        trust="configured_external",
        version="1.0",
        toolset=toolset,
        side_effects="external",
        principal_mode="none",
        idempotency="supported",
        approval_policy="default",
        data_classification="internal",
    )


class RegistrationHarness:
    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.fake_registry = ToolRegistry()
        self.monkeypatch.setattr("hermes.tools.registry.registry", self.fake_registry)

    async def register(self, path: str, raw_tools: list, utilities: list = None):
        if utilities is None:
            utilities = []
        server_name = "test_server"
        config = {"tools": {}}

        def fake_select_utilities(name, server, cfg):
            return [{"schema": {"name": f"mcp__{server_name}__{u.name}", "description": "util"}, "handler_key": "list_resources"} for u in utilities]

        self.monkeypatch.setattr("hermes.tools.mcp_tool._select_utility_schemas", fake_select_utilities)
        self.monkeypatch.setattr("hermes.tools.mcp_schema_cache.write_cache_entry", lambda *args, **kwargs: None)

        server = MCPServerTask(server_name)
        server.session = MagicMock()
        server._tools = raw_tools
        server.tool_timeout = 300

        if path == "eager":
            registered = _register_server_tools(server_name, server, config)
        elif path == "lazy":
            entry = {
                "tools": [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in raw_tools],
                "utility_tools": [{"schema": {"name": f"mcp__{server_name}__{u.name}", "description": "util"}, "handler_key": "list_resources"} for u in utilities]
            }
            registered = _register_from_cache_sync(server_name, config, entry)
        elif path == "refresh":
            session_mock = MagicMock()
            async def fake_list_tools():
                res = MagicMock()
                res.tools = raw_tools
                res.nextCursor = None
                return res
            session_mock.list_tools = fake_list_tools
            server.session = session_mock
            # _refresh_tools is async
            try:
                await server._refresh_tools()
                registered = list(server._registered_tool_names)
            except ValueError:
                registered = []
        else:
            raise ValueError(f"Unknown path: {path}")

        return registered


@pytest.fixture
def registration_harness(monkeypatch):
    return RegistrationHarness(monkeypatch)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["eager", "lazy", "refresh"])
async def test_registration_path_rejects_raw_utility_collision(path, registration_harness):
    registered = await registration_harness.register(
        path=path,
        raw_tools=[fake_tool("list_resources")],
        utilities=[fake_resource_utility("list_resources")],
    )
    assert registered == []
    assert list(registration_harness.fake_registry._tools.keys()) == []


@pytest.mark.asyncio
async def test_eager_and_lazy_register_alias_atomically(registration_harness):
    # Eager path
    eager_reg = await registration_harness.register(path="eager", raw_tools=[fake_tool("t1")])
    assert eager_reg == ["mcp__test_server__t1"]
    assert registration_harness.fake_registry._toolset_aliases.get("test_server") == "mcp-test_server"

    # Reset registry
    registration_harness.fake_registry = ToolRegistry()
    registration_harness.monkeypatch.setattr("hermes.tools.registry.registry", registration_harness.fake_registry)

    # Lazy path
    lazy_reg = await registration_harness.register(path="lazy", raw_tools=[fake_tool("t1")])
    assert lazy_reg == ["mcp__test_server__t1"]
    assert registration_harness.fake_registry._toolset_aliases.get("test_server") == "mcp-test_server"


def test_validator_rejects_schema_with_internal_toolset_field():
    cand = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema={"name": "mcp__s__t1", "_internal_toolset_name": "mcp-s"},
        handler=lambda x: x,
        check_fn=None,
        descriptor=make_descriptor("mcp__s__t1", "mcp-s"),
    )
    res = validate_registration_candidates([cand], ownership_snapshot={})
    assert len(res.accepted) == 0
    assert len(res.rejected) == 1
    assert "internal field" in res.rejected[0].reason.lower() or "_internal_toolset_name" in res.rejected[0].reason.lower()


def test_validator_rejects_descriptor_wire_name_and_toolset_mismatch():
    # Wire name mismatch
    desc_wrong_wire = make_descriptor("other_wire", "mcp-s")
    cand1 = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema={"name": "mcp__s__t1"},
        handler=lambda x: x,
        check_fn=None,
        descriptor=desc_wrong_wire,
    )
    res1 = validate_registration_candidates([cand1], ownership_snapshot={})
    assert len(res1.accepted) == 0
    assert len(res1.rejected) == 1

    # Toolset mismatch
    desc_wrong_ts = make_descriptor("mcp__s__t1", "other-toolset")
    cand2 = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema={"name": "mcp__s__t1"},
        handler=lambda x: x,
        check_fn=None,
        descriptor=desc_wrong_ts,
    )
    res2 = validate_registration_candidates([cand2], ownership_snapshot={"mcp__s__t1": "mcp-s"})
    assert len(res2.accepted) == 0
    assert len(res2.rejected) == 1


def test_commit_toolset_batch_atomic_rollback_and_single_gen_increment():
    reg = ToolRegistry()
    initial_gen = reg._generation

    cand1 = BatchRegistrationCandidate(
        name="mcp__s__t1",
        toolset="mcp-s",
        schema={"name": "mcp__s__t1"},
        handler=lambda x: x,
        descriptor=make_descriptor("mcp__s__t1", "mcp-s"),
    )

    # Single gen increment when batch succeeds with alias
    committed = reg.commit_toolset_batch(
        toolset="mcp-s",
        candidates=[cand1],
        aliases={"s": "mcp-s"},
    )
    assert committed == ("mcp__s__t1",)
    assert reg._generation == initial_gen + 1
    assert reg._toolset_aliases["s"] == "mcp-s"

    # Conflicting candidate raises RegistrationConflictError and rolls back completely
    bad_cand = BatchRegistrationCandidate(
        name="mcp__s__t1",
        toolset="other-toolset",  # mismatch toolset
        schema={"name": "mcp__s__t1"},
        handler=lambda x: x,
        descriptor=make_descriptor("mcp__s__t1", "other-toolset"),
    )
    gen_before_fail = reg._generation
    with pytest.raises(BatchCommitError):
        reg.commit_toolset_batch(
            toolset="other-toolset",
            candidates=[bad_cand],
            aliases={"other": "other-toolset"},
        )

    # Generation unchanged and alias rolled back
    assert reg._generation == gen_before_fail
    assert "other" not in reg._toolset_aliases


def test_commit_toolset_batch_zero_candidates_no_op():
    reg = ToolRegistry()
    gen = reg._generation
    res = reg.commit_toolset_batch(toolset="mcp-s", candidates=[], replace_names=None, aliases=None)
    assert res == ()
    assert reg._generation == gen


@pytest.mark.asyncio
async def test_refresh_rejected_candidate_keeps_old_tools_and_provenance(registration_harness, monkeypatch):
    # Register initial tool
    await registration_harness.register(path="eager", raw_tools=[fake_tool("t1")])
    assert "mcp__test_server__t1" in registration_harness.fake_registry._tools
    assert _mcp_tool_server_names.get("mcp__test_server__t1") == "test_server"

    # Mock refresh list_tools to return collision tools (read-file and read_file)
    session_mock = MagicMock()
    async def fake_list_tools():
        res = MagicMock()
        res.tools = [fake_tool("read-file"), fake_tool("read_file")]
        res.nextCursor = None
        return res
    session_mock.list_tools = fake_list_tools

    server = MCPServerTask("test_server")
    server.session = session_mock

    # Refresh should fail due to collision and retain old tools & provenance
    with pytest.raises(ValueError):
        await server._refresh_tools()

    assert "mcp__test_server__t1" in registration_harness.fake_registry._tools
    assert _mcp_tool_server_names.get("mcp__test_server__t1") == "test_server"


@pytest.mark.asyncio
async def test_successful_refresh_removes_stale_provenance(registration_harness):
    # Setup initial tool t1
    await registration_harness.register(path="eager", raw_tools=[fake_tool("t1")])
    assert _mcp_tool_server_names.get("mcp__test_server__t1") == "test_server"

    # Refresh with tool t2
    session_mock = MagicMock()
    async def fake_list_tools():
        res = MagicMock()
        res.tools = [fake_tool("t2")]
        res.nextCursor = None
        return res
    session_mock.list_tools = fake_list_tools

    server = MCPServerTask("test_server")
    server.session = session_mock
    server._registered_tool_names = ["mcp__test_server__t1"]

    await server._refresh_tools()

    # t1 should be removed from registry and provenance; t2 added
    assert "mcp__test_server__t1" not in registration_harness.fake_registry._tools
    assert "mcp__test_server__t1" not in _mcp_tool_server_names
    assert "mcp__test_server__t2" in registration_harness.fake_registry._tools
    assert _mcp_tool_server_names.get("mcp__test_server__t2") == "test_server"


def test_server_name_with_hyphens_descriptor_validation():
    # Server with hyphen: foo-bar -> wire name: mcp__foo_bar__tool_a -> descriptor toolset: mcp-foo-bar
    desc = make_descriptor("mcp__foo_bar__tool_a", "mcp-foo-bar")
    cand = RegistrationCandidate(
        registry_name="mcp__foo_bar__tool_a",
        raw_name="tool_a",
        origin="tool 'tool_a'",
        schema={"name": "mcp__foo_bar__tool_a"},
        handler=lambda x: x,
        check_fn=None,
        descriptor=desc,
    )
    res = validate_registration_candidates([cand], ownership_snapshot={})
    assert len(res.accepted) == 1
    assert len(res.rejected) == 0


def test_validator_deduplicates_exact_duplicates():
    desc = make_descriptor("mcp__s__t1", "mcp-s")
    handler = lambda x: x
    cand1 = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema={"name": "mcp__s__t1"},
        handler=handler,
        check_fn=None,
        descriptor=desc,
    )
    cand2 = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema={"name": "mcp__s__t1"},
        handler=handler,
        check_fn=None,
        descriptor=desc,
    )
    res = validate_registration_candidates([cand1, cand2], ownership_snapshot={})
    assert len(res.accepted) == 1
    assert len(res.rejected) == 0


def test_commit_toolset_batch_fails_closed_when_descriptor_is_none():
    reg = ToolRegistry()
    bad_cand = BatchRegistrationCandidate(
        name="mcp__s__t1",
        toolset="mcp-s",
        schema={"name": "mcp__s__t1"},
        handler=lambda x: x,
        descriptor=None,
    )
    with pytest.raises(BatchCommitError):
        reg.commit_toolset_batch(toolset="mcp-s", candidates=[bad_cand])


def test_validator_rejects_candidates_with_different_handlers_or_origins():
    desc = make_descriptor("mcp__s__t1", "mcp-s")
    h1 = lambda x: 1
    h2 = lambda x: 2
    cand1 = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema={"name": "mcp__s__t1"},
        handler=h1,
        check_fn=None,
        descriptor=desc,
    )
    cand2 = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema={"name": "mcp__s__t1"},
        handler=h2,  # Different handler!
        check_fn=None,
        descriptor=desc,
    )
    res = validate_registration_candidates([cand1, cand2], ownership_snapshot={})
    assert len(res.accepted) == 0
    assert len(res.rejected) == 2


@pytest.mark.asyncio
async def test_eager_and_refresh_paths_share_same_collect_live_candidates(monkeypatch):
    from hermes.tools.mcp_tool import collect_live_candidates
    calls = []

    def spy_collect(*args, **kwargs):
        calls.append(args)
        return collect_live_candidates(*args, **kwargs)

    monkeypatch.setattr("hermes.tools.mcp_tool.collect_live_candidates", spy_collect)
    monkeypatch.setattr("hermes.tools.mcp_schema_cache.write_cache_entry", lambda *a, **k: None)
    reg = ToolRegistry()
    monkeypatch.setattr("hermes.tools.registry.registry", reg)

    server = MCPServerTask("srv1")
    server.session = MagicMock()
    server._tools = [fake_tool("t1")]

    # Call eager
    _register_server_tools("srv1", server, {})
    assert len(calls) == 1

    # Call refresh
    session_mock = MagicMock()
    async def fake_list_tools():
        res = MagicMock()
        res.tools = [fake_tool("t1")]
        res.nextCursor = None
        return res
    session_mock.list_tools = fake_list_tools
    server.session = session_mock
    server._registered_tool_names = ["mcp__srv1__t1"]

    await server._refresh_tools()
    assert len(calls) == 2


def test_eager_path_runs_without_monkeypatching_utility_schemas(monkeypatch):
    reg = ToolRegistry()
    monkeypatch.setattr("hermes.tools.registry.registry", reg)
    monkeypatch.setattr("hermes.tools.mcp_schema_cache.write_cache_entry", lambda *a, **k: None)

    server = MCPServerTask("srv_real")
    server._tools = [fake_tool("t1")]

    registered = _register_server_tools("srv_real", server, {})
    assert registered == ["mcp__srv_real__t1"]
    assert "mcp__srv_real__t1" in reg._tools


def test_commit_toolset_batch_rejects_alias_target_mismatch_and_existing_owner_collision():
    reg = ToolRegistry()
    cand = BatchRegistrationCandidate(
        name="mcp__s__t1",
        toolset="mcp-s",
        schema={"name": "mcp__s__t1"},
        handler=lambda x: x,
        descriptor=make_descriptor("mcp__s__t1", "mcp-s"),
    )

    # Target toolset mismatch raises RegistrationConflictError
    with pytest.raises(BatchCommitError):
        reg.commit_toolset_batch(
            toolset="mcp-s",
            candidates=[cand],
            aliases={"s": "other-toolset"},
        )

    # Existing alias owner collision raises RegistrationConflictError
    reg.commit_toolset_batch(toolset="mcp-s", candidates=[cand], aliases={"s": "mcp-s"})
    cand2 = BatchRegistrationCandidate(
        name="mcp__s2__t2",
        toolset="mcp-s2",
        schema={"name": "mcp__s2__t2"},
        handler=lambda x: x,
        descriptor=make_descriptor("mcp__s2__t2", "mcp-s2"),
    )
    with pytest.raises(BatchCommitError):
        reg.commit_toolset_batch(
            toolset="mcp-s2",
            candidates=[cand2],
            aliases={"s": "mcp-s2"},  # 's' is owned by 'mcp-s'
        )


def test_validator_rejects_malformed_schema_and_missing_handler():
    desc = make_descriptor("mcp__s__t1", "mcp-s")
    # Schema not a dict
    cand1 = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema="invalid_schema",
        handler=lambda x: x,
        check_fn=None,
        descriptor=desc,
    )
    res1 = validate_registration_candidates([cand1], {})
    assert len(res1.accepted) == 0
    assert "Malformed schema" in res1.rejected[0].reason

    # Schema name mismatch
    cand2 = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema={"name": "wrong_name"},
        handler=lambda x: x,
        check_fn=None,
        descriptor=desc,
    )
    res2 = validate_registration_candidates([cand2], {})
    assert len(res2.accepted) == 0
    assert "Schema name" in res2.rejected[0].reason

    # Non-callable handler
    cand3 = RegistrationCandidate(
        registry_name="mcp__s__t1",
        raw_name="t1",
        origin="tool 't1'",
        schema={"name": "mcp__s__t1"},
        handler=None,  # Missing handler
        check_fn=None,
        descriptor=desc,
    )
    res3 = validate_registration_candidates([cand3], {})
    assert len(res3.accepted) == 0
    assert "Missing or non-callable handler" in res3.rejected[0].reason


@pytest.mark.asyncio
async def test_refresh_to_zero_tools_cleans_old_tools_provenance_checks_and_orphan_aliases(registration_harness):
    # Setup initial tool t1
    await registration_harness.register(path="eager", raw_tools=[fake_tool("t1")])
    assert "mcp__test_server__t1" in registration_harness.fake_registry._tools
    assert _mcp_tool_server_names.get("mcp__test_server__t1") == "test_server"
    assert registration_harness.fake_registry._toolset_aliases.get("test_server") == "mcp-test_server"

    gen_before = registration_harness.fake_registry._generation

    # Refresh with 0 tools
    session_mock = MagicMock()
    async def fake_list_tools():
        res = MagicMock()
        res.tools = []
        res.nextCursor = None
        return res
    session_mock.list_tools = fake_list_tools

    server = MCPServerTask("test_server")
    server.session = session_mock
    server._registered_tool_names = ["mcp__test_server__t1"]

    await server._refresh_tools()

    # All tools, provenance, checks, and orphan alias removed
    assert "mcp__test_server__t1" not in registration_harness.fake_registry._tools
    assert "mcp__test_server__t1" not in _mcp_tool_server_names
    assert "mcp-test_server" not in registration_harness.fake_registry._toolset_checks
    assert "test_server" not in registration_harness.fake_registry._toolset_aliases
    assert server._registered_tool_names == []
    # Generation incremented exactly once
    assert registration_harness.fake_registry._generation == gen_before + 1



