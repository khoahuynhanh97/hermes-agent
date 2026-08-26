"""Unit tests for AgentTurnRuntime channel convergence boundary."""
from __future__ import annotations

import pytest
from hermes.agent.turn_runtime import AgentTurnRequest, AgentTurnResult, AgentTurnRuntime
from hermes.security.principal import PrincipalContext, current_principal


class FakeAgent:
    def __init__(self):
        self.last_user_message = None
        self.captured_principal = None
        self.closed = False

    def run_conversation(self, user_message: str, conversation_history: list = None, task_id: str = None) -> dict:
        self.last_user_message = user_message
        self.captured_principal = current_principal.get()
        return {
            "content": f"Echo: {user_message}",
            "messages": [{"role": "user", "content": user_message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    def close(self) -> None:
        self.closed = True


def test_turn_runtime_executes_within_principal_scope():
    agent = FakeAgent()
    runtime = AgentTurnRuntime(agent)
    princ = PrincipalContext(actor_id="usr_123", owner_user_id="usr_123", platform="telegram", session_id="sess_456")

    req = AgentTurnRequest(message="hello world", principal=princ)
    res = runtime.run(req)

    assert res.content == "Echo: hello world"
    assert agent.captured_principal is princ
    assert current_principal.get() is None


def test_turn_runtime_builds_channel_agent_and_normalizes_final_response():
    created = {}

    class FactoryAgent(FakeAgent):
        def run_conversation(self, user_message: str, conversation_history: list = None, task_id: str = None) -> dict:
            created["history"] = conversation_history
            created["task_id"] = task_id
            created["principal"] = current_principal.get()
            return {
                "final_response": "Hermes completed the turn",
                "messages": [{"role": "assistant", "content": "Hermes completed the turn"}],
                "usage": {"total_tokens": 12},
            }

    agent = FactoryAgent()

    def factory(request):
        created["request"] = request
        return agent

    principal = PrincipalContext(
        actor_id="42",
        owner_user_id="42",
        platform="telegram",
        session_id="telegram:100",
    )
    request = AgentTurnRequest(
        message="create a product video",
        principal=principal,
        platform="telegram",
        conversation_history=({"role": "user", "content": "previous"},),
    )

    result = AgentTurnRuntime(agent_factory=factory).run(request)

    assert created["request"] is request
    assert created["history"] == [{"role": "user", "content": "previous"}]
    assert created["task_id"] == "telegram:100"
    assert created["principal"] is principal
    assert result.content == "Hermes completed the turn"
    assert result.session_id == "telegram:100"
    assert result.completed is True
    assert agent.closed is True


def test_default_agent_factory_discovers_mcp_before_tool_snapshot(monkeypatch):
    from hermes.agent import runtime_agent
    from hermes.channels.cli import mcp_startup

    calls = []

    class ConstructedAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(
        mcp_startup,
        "ensure_mcp_discovery_before_agent_build",
        lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(runtime_agent, "AIAgent", ConstructedAgent)
    principal = PrincipalContext(
        actor_id="42",
        owner_user_id="42",
        platform="telegram",
        session_id="telegram:100",
    )

    agent = AgentTurnRuntime._default_agent_factory(
        AgentTurnRequest(message="research product", principal=principal, platform="telegram")
    )

    assert calls and calls[0]["single_query"] is True
    assert agent.kwargs["platform"] == "telegram"
