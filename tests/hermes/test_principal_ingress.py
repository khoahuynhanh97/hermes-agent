import pytest
from hermes.security.principal import (
    PrincipalContext,
    bind_principal_arguments,
    current_principal,
    set_current_principal,
)


def test_first_party_owner_argument_is_bound_from_principal():
    principal = PrincipalContext("actor-1", "owner-1", "cli", "session-1", ("admin",))
    args = bind_principal_arguments(
        {"owner_user_id": "impersonated", "run_id": "run-1"},
        principal,
        principal_mode="session",
    )
    assert args["owner_user_id"] == "owner-1"


def test_principal_context_var_lifecycle():
    principal = PrincipalContext("actor-1", "owner-1", "cli", "session-1", ("admin",))
    token = set_current_principal(principal)
    try:
        assert current_principal.get() == principal
        assert current_principal.get().owner_user_id == "owner-1"
    finally:
        current_principal.reset(token)
    assert current_principal.get() is None


def test_session_scoped_dispatch_overwrites_model_owner():
    from hermes.tools.registry import registry
    from hermes.security import PrincipalContext, set_current_principal, current_principal

    received_args = {}

    def sample_handler(args, **kwargs):
        received_args.update(args)
        return "ok"

    registry.register(
        name="test_session_tool_ow",
        toolset="test_ts",
        schema={"name": "test_session_tool_ow", "description": "test tool"},
        handler=sample_handler,
    )

    principal = PrincipalContext("actor-99", "real-authenticated-owner", "cli", "session-99")
    token = set_current_principal(principal)
    try:
        res = registry.dispatch("test_session_tool_ow", {"owner_user_id": "attacker-model-input", "data": "123"})
        assert res == "ok"
        assert received_args["owner_user_id"] == "real-authenticated-owner"
    finally:
        current_principal.reset(token)


def test_session_scoped_dispatch_rejects_missing_principal():
    from hermes.tools.registry import registry
    from hermes.security import current_principal

    current_principal.set(None)

    def sample_handler(args, **kwargs):
        return "ok"

    registry.register(
        name="test_session_tool_strict",
        toolset="test_ts",
        schema={"name": "test_session_tool_strict", "description": "test tool"},
        handler=sample_handler,
    )

    res = registry.dispatch("test_session_tool_strict", {"data": "123"})
    assert "error" in str(res)
    assert "Principal context is required" in str(res)


def test_non_session_tool_does_not_receive_injected_owner():
    from hermes.tools.registry import registry
    from hermes.security import PrincipalContext, set_current_principal, current_principal

    received_args = {}

    def sample_ext_handler(args, **kwargs):
        received_args.update(args)
        return "ok"

    from hermes.capabilities.policies import CapabilityPolicyResolver
    desc = CapabilityPolicyResolver().resolve_mcp("external_srv", {}, "mcp__external_srv__ext_tool")
    registry.register(
        name="mcp__external_srv__ext_tool",
        toolset="mcp-external_srv",
        schema={"name": "mcp__external_srv__ext_tool", "description": "external tool"},
        handler=sample_ext_handler,
        descriptor=desc,
    )

    principal = PrincipalContext("actor-99", "real-authenticated-owner", "cli", "session-99")
    token = set_current_principal(principal)
    try:
        res = registry.dispatch("mcp__external_srv__ext_tool", {"query": "hello"})
        assert res == "ok"
        assert "owner_user_id" not in received_args
    finally:
        current_principal.reset(token)


def test_principal_has_no_implicit_admin_role():
    principal = PrincipalContext(
        actor_id="actor-1",
        owner_user_id="owner-1",
        platform="telegram",
        session_id="session-1",
    )
    assert principal.roles == ()


def test_dispatch_uses_descriptor_principal_mode():
    from hermes.tools.registry import registry
    from hermes.security import PrincipalContext, set_current_principal, current_principal

    received = {}
    def sample_fn(args, **kwargs):
        received.update(args)
        return "ok"

    from hermes.capabilities.models import CapabilityDescriptor
    registry.register(
        name="test_desc_mode_tool",
        toolset="test",
        schema={"name": "test_desc_mode_tool"},
        handler=sample_fn,
        descriptor=CapabilityDescriptor(
            capability_id="cap_test", wire_name="test_desc_mode_tool", owner="test",
            source="native", trust="first_party", version="1.0", toolset="test",
            side_effects="read", principal_mode="none", idempotency="supported",
            approval_policy="default", data_classification="internal"
        ),
    )

    principal = PrincipalContext("actor-1", "owner-1", "cli", "s-1")
    token = set_current_principal(principal)
    try:
        res = registry.dispatch("test_desc_mode_tool", {"arg": "val"})
        assert res == "ok"
        assert "owner_user_id" not in received
    finally:
        current_principal.reset(token)


def test_unknown_sensitive_capability_fails_closed():
    from hermes.tools.registry import registry
    from hermes.security import current_principal
    current_principal.set(None)
    res = registry.dispatch("non_existent_tool_xyz", {"data": "123"})
    assert "Unknown tool" in str(res)


def test_external_mcp_does_not_receive_session_owner():
    from hermes.tools.registry import registry
    from hermes.security import PrincipalContext, set_current_principal, current_principal

    received = {}
    def sample_ext(args, **kwargs):
        received.update(args)
        return "ok"

    from hermes.capabilities.policies import CapabilityPolicyResolver
    desc = CapabilityPolicyResolver().resolve_mcp("unmanaged_ext", {}, "mcp__unmanaged_ext__search")
    registry.register(
        name="mcp__unmanaged_ext__search",
        toolset="mcp-unmanaged_ext",
        schema={"name": "mcp__unmanaged_ext__search"},
        handler=sample_ext,
        descriptor=desc,
    )

    principal = PrincipalContext("actor-1", "owner-1", "cli", "s-1")
    token = set_current_principal(principal)
    try:
        res = registry.dispatch("mcp__unmanaged_ext__search", {"query": "test"})
        assert res == "ok"
        assert "owner_user_id" not in received
    finally:
        current_principal.reset(token)


def test_session_capability_overwrites_spoofed_owner():
    from hermes.tools.registry import registry
    from hermes.security import PrincipalContext, set_current_principal, current_principal

    received = {}
    def sample_session_fn(args, **kwargs):
        received.update(args)
        return "ok"

    from hermes.capabilities.policies import CapabilityPolicyResolver
    # Provide a config that specifies session mode so the spoofing check works
    desc = CapabilityPolicyResolver().resolve_mcp("hermes_research", {"capability": {"principal_mode": "session", "owner": "hermes"}}, "mcp__hermes_research__research_fetch")
    registry.register(
        name="mcp__hermes_research__research_fetch",
        toolset="mcp-hermes_research",
        schema={"name": "mcp__hermes_research__research_fetch"},
        handler=sample_session_fn,
        descriptor=desc,
    )

    principal = PrincipalContext("actor-1", "authentic-owner-99", "cli", "s-1")
    token = set_current_principal(principal)
    try:
        res = registry.dispatch("mcp__hermes_research__research_fetch", {"owner_user_id": "spoofed-attacker"})
        assert res == "ok"
        assert received["owner_user_id"] == "authentic-owner-99"
    finally:
        current_principal.reset(token)


def test_internal_none_mode_tool_runs_without_principal():
    from hermes.tools.registry import registry
    from hermes.security import current_principal
    from hermes.capabilities.models import CapabilityDescriptor

    current_principal.set(None)

    def sample_none_fn(args, **kwargs):
        return "ok_none"

    registry.register(
        name="test_internal_none_tool",
        toolset="test",
        schema={"name": "test_internal_none_tool"},
        handler=sample_none_fn,
        descriptor=CapabilityDescriptor(
            capability_id="cap_none", wire_name="test_internal_none_tool", owner="hermes",
            source="native", trust="first_party", version="1.0", toolset="test",
            side_effects="read", principal_mode="none", idempotency="supported",
            approval_policy="default", data_classification="internal"
        ),
    )

    res = registry.dispatch("test_internal_none_tool", {"arg": "val"})
    assert res == "ok_none"


def test_nested_call_preserves_ingress_principal():
    from hermes.security import PrincipalContext, set_current_principal, current_principal
    from hermes.agent.runtime_agent import AIAgent

    ingress_principal = PrincipalContext("user-1", "user-1", "telegram", "chat-100")
    token = set_current_principal(ingress_principal)

    try:
        agent = AIAgent(model="mock")
        assert current_principal.get() == ingress_principal
        assert current_principal.get().platform == "telegram"
    finally:
        current_principal.reset(token)
