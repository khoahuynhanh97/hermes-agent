from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from hermes_personal.contracts import AttachmentRef, ChannelCapabilities
from hermes_personal.identity import IdentityRepository, UnknownIdentity
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect


@pytest.fixture
def gateway_repositories(tmp_path):
    connection = connect(tmp_path / "gateway.sqlite")
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    owner = identities.create_owner("Khoa")
    for channel in ("telegram", "cli", "web", "omni"):
        identities.link(owner.owner_user_id, channel, "subject:khoa")
    try:
        yield connection, identities, sessions, owner
    finally:
        connection.close()


@pytest.fixture
def normalizer_factory(gateway_repositories):
    _, identities, sessions, _ = gateway_repositories

    def create(channel: str):
        from hermes_personal.gateway.normalizers import ChannelTurnNormalizer

        return ChannelTurnNormalizer(channel, identities, sessions)

    return create


@pytest.mark.parametrize("channel", ("telegram", "cli", "web", "omni"))
def test_natural_language_channels_share_one_canonical_request_contract(
    channel, normalizer_factory, gateway_repositories
):
    _, _, _, owner = gateway_repositories

    request = normalizer_factory(channel).normalize(
        external_subject="subject:khoa",
        external_conversation_id="conversation:7",
        message="Tim san pham cong nghe 200-500k",
    )

    assert request.channel == channel
    assert request.message == "Tim san pham cong nghe 200-500k"
    assert request.principal.actor_id == "subject:khoa"
    assert request.principal.owner_user_id == owner.owner_user_id
    assert request.idempotency_key == request.turn_id
    assert isinstance(request.channel_capabilities, ChannelCapabilities)


def test_normalizer_preserves_attachment_tuple_capabilities_and_authenticated_idempotency(
    normalizer_factory,
):
    attachment = AttachmentRef(
        attachment_id="asset_1",
        kind="document",
        media_type="application/pdf",
        uri="hermes://assets/asset_1",
    )
    capabilities = ChannelCapabilities(
        streaming=True,
        interactive_controls=True,
        attachments=True,
    )

    request = normalizer_factory("web").normalize(
        external_subject="subject:khoa",
        external_conversation_id="browser:7",
        message="",
        attachments=(attachment,),
        channel_capabilities=capabilities,
        authenticated_idempotency_key="transport:web:evt-7",
    )

    assert request.attachments == (attachment,)
    assert request.channel_capabilities is capabilities
    assert request.idempotency_key == "transport:web:evt-7"


def test_unknown_identity_fails_before_creating_a_session(
    normalizer_factory, gateway_repositories
):
    connection, _, _, _ = gateway_repositories

    with pytest.raises(UnknownIdentity):
        normalizer_factory("telegram").normalize(
            external_subject="subject:unknown",
            external_conversation_id="conversation:unknown",
            message="hello",
        )

    count = connection.execute(
        "SELECT COUNT(*) AS count FROM conversation_session"
    ).fetchone()["count"]
    assert count == 0


@pytest.mark.parametrize(
    ("channel", "external_subject", "external_conversation_id", "message"),
    (
        ("email", "subject:khoa", "conversation:7", "hello"),
        ("web", "   ", "conversation:7", "hello"),
        ("web", "subject:khoa", "   ", "hello"),
        ("web", "subject:khoa", "conversation:7", "   "),
    ),
)
def test_normalizer_rejects_unknown_channels_and_blank_inputs(
    channel,
    external_subject,
    external_conversation_id,
    message,
    normalizer_factory,
):
    with pytest.raises(ValueError):
        normalizer_factory(channel).normalize(
            external_subject=external_subject,
            external_conversation_id=external_conversation_id,
            message=message,
        )


def test_normalizer_rejects_blank_authenticated_idempotency_key(normalizer_factory):
    with pytest.raises(ValueError, match="authenticated_idempotency_key"):
        normalizer_factory("cli").normalize(
            external_subject="subject:khoa",
            external_conversation_id="terminal:7",
            message="hello",
            authenticated_idempotency_key="   ",
        )


def test_workflow_is_allowed_only_for_active_session_or_same_owner_handoff(
    normalizer_factory, gateway_repositories
):
    _, _, sessions, owner = gateway_repositories
    source = sessions.get_or_create(owner.owner_user_id, "telegram", "source:7")
    sessions.link_workflow(source.session_id, "wf_7")

    active_request = normalizer_factory("telegram").normalize(
        external_subject="subject:khoa",
        external_conversation_id="source:7",
        message="continue",
        workflow_id="wf_7",
    )
    assert active_request.workflow_id == "wf_7"

    target = sessions.get_or_create(owner.owner_user_id, "cli", "target:7")
    sessions.create_handoff(
        owner.owner_user_id,
        "wf_7",
        source.session_id,
        target.session_id,
    )
    handoff_request = normalizer_factory("cli").normalize(
        external_subject="subject:khoa",
        external_conversation_id="target:7",
        message="continue",
        workflow_id="wf_7",
    )
    assert handoff_request.workflow_id == "wf_7"


def test_workflow_is_denied_before_request_creation_when_not_authorized(
    normalizer_factory, gateway_repositories
):
    _, _, sessions, owner = gateway_repositories
    session = sessions.get_or_create(owner.owner_user_id, "web", "browser:7")

    with pytest.raises(PermissionError, match="workflow is not authorized"):
        normalizer_factory("web").normalize(
            external_subject="subject:khoa",
            external_conversation_id="browser:7",
            message="continue",
            workflow_id="wf_denied",
        )

    assert sessions.get(session.session_id).active_workflow_id is None


def test_unauthorized_workflow_for_new_conversation_creates_no_session(
    normalizer_factory, gateway_repositories
):
    connection, _, _, _ = gateway_repositories

    with pytest.raises(PermissionError, match="workflow is not authorized"):
        normalizer_factory("web").normalize(
            external_subject="subject:khoa",
            external_conversation_id="new-browser:7",
            message="continue",
            workflow_id="wf_denied",
        )

    count = connection.execute(
        "SELECT COUNT(*) AS count FROM conversation_session"
    ).fetchone()["count"]
    assert count == 0


class PublicState:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def set(self, key: str, value: object) -> None:
        json.dumps(value)
        self.values[key] = value


class PublicPluginContext:
    def __init__(self, profile_name: str = "personal") -> None:
        self.profile_name = profile_name
        self.state = PublicState()
        self.unload_callbacks = []
        self.spawn_task_called = False

    def on_unload(self, callback):
        self.unload_callbacks.append(callback)

    def spawn_task(self, coro, *, name=None):
        self.spawn_task_called = True
        raise AssertionError("no lifecycle coroutine exists for this plugin")

    @property
    def _manager(self):
        raise AssertionError("plugin must not use private PluginContext fields")


def test_project_plugin_uses_public_api_durable_metadata_and_cleanup():
    from hermes_personal.gateway.plugin import (
        get_turn_service,
        register,
        register_turn_service,
    )

    context = PublicPluginContext()
    service = object()
    lease = register_turn_service(context.profile_name, service)

    register(context)

    assert get_turn_service(context.profile_name) is service
    assert lease.profile_name == context.profile_name
    assert context.state.values == {
        "gateway.registration": {
            "profile_name": "personal",
            "registry": "hermes_personal.gateway.turn_service",
            "schema_version": 1,
            "generation": lease.generation,
        }
    }
    assert len(context.unload_callbacks) == 1
    assert context.spawn_task_called is False
    context.unload_callbacks[0]()
    assert get_turn_service(context.profile_name) is None


def test_plugin_package_delegates_and_never_registers_a_platform(monkeypatch):
    import plugins.hermes_personal as project_plugin

    calls = []
    context = PublicPluginContext()
    monkeypatch.setattr(project_plugin, "register_gateway", calls.append)

    project_plugin.register(context)

    assert calls == [context]


def test_stale_same_profile_unload_does_not_remove_replacement_service():
    from hermes_personal.gateway.plugin import (
        get_turn_service,
        register,
        register_turn_service,
    )

    first_context = PublicPluginContext("replacement")
    first_service = object()
    first_lease = register_turn_service("replacement", first_service)
    register(first_context)

    second_context = PublicPluginContext("replacement")
    second_service = object()
    second_lease = register_turn_service("replacement", second_service)
    register(second_context)

    assert first_lease.generation < second_lease.generation
    first_context.unload_callbacks[0]()
    assert get_turn_service("replacement") is second_service

    second_context.unload_callbacks[0]()
    assert get_turn_service("replacement") is None


def test_turn_service_registry_isolated_across_profiles():
    from hermes_personal.gateway.plugin import (
        get_turn_service,
        register,
        register_turn_service,
    )

    first_context = PublicPluginContext("profile-one")
    second_context = PublicPluginContext("profile-two")
    first_service = object()
    second_service = object()
    register_turn_service("profile-one", first_service)
    register_turn_service("profile-two", second_service)
    register(first_context)
    register(second_context)

    first_context.unload_callbacks[0]()

    assert get_turn_service("profile-one") is None
    assert get_turn_service("profile-two") is second_service
    second_context.unload_callbacks[0]()


def test_real_plugin_manifest_is_discovered_without_kind_coercion_and_delegates(
    tmp_path, monkeypatch, caplog
):
    from hermes_cli import plugins as plugins_module
    from hermes_cli.plugins import PluginManager, PluginState
    import plugins.hermes_personal as project_plugin

    source_plugin = Path(__file__).resolve().parents[3] / "plugins" / "hermes_personal"
    bundled_plugins = tmp_path / "bundled"
    test_plugin = bundled_plugins / "hermes_personal"
    test_plugin.mkdir(parents=True)
    (test_plugin / "plugin.yaml").write_text(
        (source_plugin / "plugin.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (test_plugin / "__init__.py").write_text(
        "from plugins.hermes_personal import register\n",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - hermes-personal\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(
        plugins_module, "get_bundled_plugins_dir", lambda: bundled_plugins
    )
    calls = []
    original_register = project_plugin.register_gateway

    def record_public_context(ctx):
        calls.append(ctx)
        return original_register(ctx)

    monkeypatch.setattr(project_plugin, "register_gateway", record_public_context)
    manager = PluginManager()
    with caplog.at_level(logging.WARNING, logger="hermes_cli.plugins"):
        manager.discover_and_load()

    loaded = manager._plugins["hermes-personal"]
    assert loaded.manifest.kind == "standalone"
    assert loaded.enabled is True
    assert len(calls) == 1
    assert PluginState("hermes-personal").get("gateway.registration")["registry"] == (
        "hermes_personal.gateway.turn_service"
    )
    assert not any("unknown kind" in record.getMessage().lower() for record in caplog.records)
    manager.unload()
