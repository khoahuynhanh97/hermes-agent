"""Unit tests for AgentTurnRuntime channel convergence boundary."""
from __future__ import annotations

import pytest
from hermes.agent.turn_runtime import AgentTurnRequest, AgentTurnResult, AgentTurnRuntime
from hermes.security.principal import PrincipalContext, current_principal


class FakeAgent:
    def __init__(self):
        self.last_user_message = None
        self.captured_principal = None

    def run_conversation(self, user_message: str, conversation_history: list = None, task_id: str = None) -> dict:
        self.last_user_message = user_message
        self.captured_principal = current_principal.get()
        return {
            "content": f"Echo: {user_message}",
            "messages": [{"role": "user", "content": user_message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }


def test_turn_runtime_executes_within_principal_scope():
    agent = FakeAgent()
    runtime = AgentTurnRuntime(agent)
    princ = PrincipalContext(actor_id="usr_123", owner_user_id="usr_123", platform="telegram", session_id="sess_456")

    req = AgentTurnRequest(message="hello world", principal=princ)
    res = runtime.run(req)

    assert res.content == "Echo: hello world"
    assert agent.captured_principal is princ
    assert current_principal.get() is None
