import pytest
import asyncio
import os
from unittest.mock import MagicMock

from hermes.security.principal import PrincipalContext, current_principal
from hermes.security.ingress import (
    principal_scope,
    build_local_cli_principal,
    build_local_oneshot_principal,
    build_gui_principal,
    build_gateway_principal,
    build_api_principal,
)


def test_nested_agent_turn_preserves_gateway_principal():
    principal = PrincipalContext("actor-1", "owner-1", "gateway", "session-1", ())
    with principal_scope(principal) as outer_bound:
        assert current_principal.get() == principal
        nested = PrincipalContext("actor-2", "owner-2", "cli", "session-2", ())
        with principal_scope(nested) as inner_bound:
            assert current_principal.get() == principal
            assert inner_bound == principal
    assert current_principal.get() is None


def test_api_without_configured_owner_returns_401(monkeypatch):
    monkeypatch.delenv("HERMES_API_OWNER_USER_ID", raising=False)
    principal = build_api_principal("session-api")
    assert principal is None


def test_api_with_configured_owner_builds_principal(monkeypatch):
    monkeypatch.setenv("HERMES_API_OWNER_USER_ID", "api-admin-1")
    principal = build_api_principal("session-api")
    assert principal is not None
    assert principal.owner_user_id == "api-admin-1"
    assert principal.platform == "api_server"


def test_gui_turn_uses_gui_platform(monkeypatch):
    monkeypatch.setenv("HERMES_GUI_OWNER_USER_ID", "gui-user-1")
    principal = build_gui_principal("session-gui")
    assert principal.platform == "gui"
    assert principal.owner_user_id == "gui-user-1"


def test_cli_principal_builds_from_env_or_os(monkeypatch):
    monkeypatch.setenv("HERMES_CLI_USER_ID", "cli-user-42")
    monkeypatch.setenv("HERMES_LOCAL_ADMIN", "true")
    principal = build_local_cli_principal("sess-cli")
    assert principal.platform == "cli"
    assert principal.owner_user_id == "cli-user-42"
    assert "admin" in principal.roles


def test_oneshot_principal_builds_from_env(monkeypatch):
    monkeypatch.setenv("HERMES_CLI_USER_ID", "oneshot-user")
    monkeypatch.setenv("HERMES_LOCAL_ADMIN", "false")
    principal = build_local_oneshot_principal("sess-oneshot")
    assert principal.platform == "oneshot"
    assert principal.owner_user_id == "oneshot-user"
    assert principal.roles == ()


def test_gateway_principal_uses_source_identity():
    principal = build_gateway_principal(
        actor_id="telegram-12345",
        owner_user_id="telegram-12345",
        platform="telegram",
        session_id="chat-6789",
    )
    assert principal.platform == "telegram"
    assert principal.actor_id == "telegram-12345"


@pytest.mark.asyncio
async def test_concurrent_principal_scopes():
    p1 = PrincipalContext("actor-1", "owner-1", "cli", "sess-1")
    p2 = PrincipalContext("actor-2", "owner-2", "gui", "sess-2")

    async def task_1():
        with principal_scope(p1):
            await asyncio.sleep(0.01)
            assert current_principal.get() == p1

    async def task_2():
        with principal_scope(p2):
            await asyncio.sleep(0.01)
            assert current_principal.get() == p2

    await asyncio.gather(task_1(), task_2())
    assert current_principal.get() is None
