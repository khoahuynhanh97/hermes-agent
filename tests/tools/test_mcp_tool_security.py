import pytest
from hermes.tools.mcp_tool import (
    _build_safe_env,
    SecretScopeError,
    collect_live_candidates,
    validate_registration_candidates,
    MCPServerTask,
)


class FakeTool:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    def __repr__(self):
        return f"FakeTool({self.name!r})"


def fake_tool(name: str) -> FakeTool:
    return FakeTool(name)


def test_external_mcp_receives_only_allowlisted_secret(monkeypatch):
    monkeypatch.setenv("PATH", "safe-path")
    monkeypatch.setenv("SECRET_A", "alpha")
    monkeypatch.setenv("SECRET_B", "beta")

    env = _build_safe_env({"SECRET_A": "${SECRET_A}"}, allowed_secret_names={"SECRET_A"})

    assert env["SECRET_A"] == "alpha"
    assert "SECRET_B" not in env


def test_external_mcp_rejects_interpolation_outside_allowlist(monkeypatch):
    monkeypatch.setenv("SECRET_A", "alpha")
    monkeypatch.setenv("SECRET_B", "beta")

    with pytest.raises(SecretScopeError):
        _build_safe_env(
            {"X": "${SECRET_B}"},
            allowed_secret_names={"SECRET_A"},
        )


def test_eager_and_lazy_discovery_reject_same_normalized_collision():
    tools = [fake_tool("read-file"), fake_tool("read_file")]
    server = MCPServerTask("s1")
    cands = collect_live_candidates("s1", server, tools, {})
    res = validate_registration_candidates(cands, {})
    assert res.accepted == ()
    assert len(res.rejected) == 2


@pytest.mark.asyncio
async def test_mcpserver_task_run_stdio_uses_secret_allowlist(monkeypatch):
    from hermes.tools.mcp_tool import MCPServerTask

    captured = {}

    def mock_build_safe_env(user_env, allowed_secret_names=None):
        captured["allowed"] = allowed_secret_names
        return {"PATH": "safe"}

    monkeypatch.setattr("hermes.tools.mcp_tool._build_safe_env", mock_build_safe_env)
    monkeypatch.setattr("hermes.tools.mcp_tool._resolve_stdio_command", lambda cmd, env: (cmd, env))

    task = MCPServerTask("test_srv")

    monkeypatch.setattr("hermes.tools.osv_check.check_package_for_malware", lambda cmd, args: None)

    try:
        await task._run_stdio({"command": "echo", "secret_allowlist": ["MY_KEY"]})
    except Exception:
        pass

    assert captured.get("allowed") == {"MY_KEY"}


def test_two_servers_with_different_allowlists_isolation(monkeypatch):
    monkeypatch.setenv("SECRET_A", "alpha")
    monkeypatch.setenv("SECRET_B", "beta")

    env_srv1 = _build_safe_env({"K1": "${SECRET_A}"}, allowed_secret_names={"SECRET_A"})
    env_srv2 = _build_safe_env({"K2": "${SECRET_B}"}, allowed_secret_names={"SECRET_B"})

    assert env_srv1.get("K1") == "alpha"
    assert "SECRET_B" not in env_srv1
    assert "K2" not in env_srv1

    assert env_srv2.get("K2") == "beta"
    assert "SECRET_A" not in env_srv2
    assert "K1" not in env_srv2


def test_build_safe_env_validates_allowlist_type():
    with pytest.raises(TypeError):
        _build_safe_env({}, allowed_secret_names="INVALID_STRING")


@pytest.mark.asyncio
async def test_run_stdio_rejects_string_secret_allowlist():
    from hermes.tools.mcp_tool import MCPServerTask
    task = MCPServerTask("srv")
    with pytest.raises(TypeError):
        await task._run_stdio({"command": "echo", "secret_allowlist": "SECRET_A"})


@pytest.mark.asyncio
async def test_run_stdio_rejects_mapping_secret_allowlist():
    from hermes.tools.mcp_tool import MCPServerTask
    task = MCPServerTask("srv")
    with pytest.raises(TypeError):
        await task._run_stdio({"command": "echo", "secret_allowlist": {"SECRET_A": "val"}})


@pytest.mark.asyncio
async def test_run_stdio_rejects_non_string_secret_name():
    from hermes.tools.mcp_tool import MCPServerTask
    task = MCPServerTask("srv")
    with pytest.raises(ValueError):
        await task._run_stdio({"command": "echo", "secret_allowlist": [123]})


@pytest.mark.asyncio
async def test_run_stdio_passes_valid_allowlist_to_safe_env(monkeypatch):
    from hermes.tools.mcp_tool import MCPServerTask
    task = MCPServerTask("srv")
    captured = {}

    def mock_build_safe_env(user_env, allowed_secret_names=None):
        captured["allowed"] = allowed_secret_names
        return {"PATH": "safe"}

    monkeypatch.setattr("hermes.tools.mcp_tool._build_safe_env", mock_build_safe_env)
    monkeypatch.setattr("hermes.tools.mcp_tool._resolve_stdio_command", lambda cmd, env: (cmd, env))
    monkeypatch.setattr("hermes.tools.osv_check.check_package_for_malware", lambda cmd, args: None)

    try:
        await task._run_stdio({"command": "echo", "secret_allowlist": ["KEY_1", "KEY_2"]})
    except Exception:
        pass

    assert captured.get("allowed") == {"KEY_1", "KEY_2"}


def test_servers_have_isolated_secret_scopes(monkeypatch):
    monkeypatch.setenv("SECRET_SERVER_1", "val1")
    monkeypatch.setenv("SECRET_SERVER_2", "val2")

    env1 = _build_safe_env({"KEY": "${SECRET_SERVER_1}"}, allowed_secret_names={"SECRET_SERVER_1"})
    env2 = _build_safe_env({"KEY": "${SECRET_SERVER_2}"}, allowed_secret_names={"SECRET_SERVER_2"})

    assert env1["KEY"] == "val1"
    assert "SECRET_SERVER_2" not in env1

    assert env2["KEY"] == "val2"
    assert "SECRET_SERVER_1" not in env2


def test_unallowlisted_secret_source_env_var_is_not_passed(monkeypatch):
    monkeypatch.setenv("UNALLOWLISTED_SECRET", "secret_val")
    monkeypatch.setattr("hermes.channels.cli.env_loader.get_secret_source", lambda k: True if k == "UNALLOWLISTED_SECRET" else None, raising=False)

    env = _build_safe_env({}, allowed_secret_names={"ALLOWED_SECRET"})
    assert "UNALLOWLISTED_SECRET" not in env


def test_substring_interpolation_outside_allowlist_raises_error(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "secret123")
    with pytest.raises(SecretScopeError):
        _build_safe_env({"HEADER": "Bearer ${SECRET_KEY}"}, allowed_secret_names={"OTHER_KEY"})


def test_substring_interpolation_inside_allowlist_substitutes(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "secret123")
    env = _build_safe_env({"HEADER": "Bearer ${SECRET_KEY}"}, allowed_secret_names={"SECRET_KEY"})
    assert env["HEADER"] == "Bearer secret123"


def test_no_allowlist_rejects_interpolation(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "secret123")
    with pytest.raises(SecretScopeError):
        _build_safe_env({"HEADER": "Bearer ${SECRET_KEY}"}, allowed_secret_names=None)


def test_env_prefix_and_special_chars_interpolation(monkeypatch):
    monkeypatch.setenv("MY-SECRET.KEY", "val123")
    env = _build_safe_env({"K": "${env:MY-SECRET.KEY}"}, allowed_secret_names={"MY-SECRET.KEY"})
    assert env["K"] == "val123"


