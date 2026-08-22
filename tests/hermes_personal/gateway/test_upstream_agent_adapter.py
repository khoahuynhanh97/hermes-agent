from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from queue import Queue as StdlibQueue
from typing import Any, Mapping

import pytest

from hermes_personal.contracts import AgentTurnRequest, PrincipalContext


@dataclass
class SpyAIAgent:
    result: Mapping[str, Any]
    on_run: Callable[[Callable[[str | None], None]], None] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def run_conversation(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        callback = kwargs["stream_callback"]
        if self.on_run is not None:
            self.on_run(callback)
        return self.result


@pytest.fixture
def agent_turn() -> AgentTurnRequest:
    return AgentTurnRequest(
        principal=PrincipalContext(
            actor_id="actor:1",
            owner_user_id="user:1",
            channel="cli",
            session_id="session:1",
        ),
        message="tao video",
        turn_id="turn_adapter",
    )


def completed_result(*, final_response: str = "ok", messages=None) -> dict[str, Any]:
    return {
        "final_response": final_response,
        "messages": messages if messages is not None else [],
        "completed": True,
        "failed": False,
        "interrupted": False,
        "provider": "test-provider",
        "input_tokens": 3,
        "output_tokens": 5,
    }


def test_adapter_calls_only_public_surface_with_canonical_arguments(agent_turn):
    from hermes_personal.orchestration.upstream_agent import UpstreamAIAgentAdapter

    history = ({"role": "user", "content": "truoc"},)
    agent = SpyAIAgent(completed_result())

    outputs = list(UpstreamAIAgentAdapter(agent).run(agent_turn, history))

    assert agent.calls == [
        {
            "user_message": "tao video",
            "conversation_history": [{"role": "user", "content": "truoc"}],
            "task_id": "turn_adapter",
            "stream_callback": agent.calls[0]["stream_callback"],
            "persist_user_message": "tao video",
        }
    ]
    assert agent.calls[0]["conversation_history"] is not history
    assert [output.event_type for output in outputs] == ["text_delta", "completed"]
    assert outputs[0].data == {"text": "ok"}
    assert outputs[-1].data["provider"] == "test-provider"


def test_adapter_yields_text_deltas_before_synchronous_call_completes(agent_turn):
    from hermes_personal.orchestration.upstream_agent import UpstreamAIAgentAdapter

    release = threading.Event()
    returned = threading.Event()

    def stream(callback):
        callback("mot ")
        callback(None)
        release.wait(1)
        callback("hai")
        returned.set()

    agent = SpyAIAgent(completed_result(final_response="mot hai"), on_run=stream)
    outputs = UpstreamAIAgentAdapter(agent).run(agent_turn, ())

    first = next(outputs)
    assert first.event_type == "text_delta"
    assert first.data == {"text": "mot "}
    assert not returned.is_set()

    release.set()
    rest = list(outputs)

    assert [(output.event_type, output.data.get("text")) for output in rest] == [
        ("text_delta", "hai"),
        ("completed", None),
    ]


def test_adapter_emits_only_new_tool_events_with_original_ids(agent_turn):
    from hermes_personal.orchestration.upstream_agent import UpstreamAIAgentAdapter

    history = (
        {
            "role": "assistant",
            "tool_calls": [{"id": "old_call", "function": {"name": "old"}}],
        },
        {"role": "tool", "tool_call_id": "old_call", "content": "old result"},
    )
    messages = [
        *history,
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_42",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": "{\"q\": \"Hermes\"}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_42", "content": "found it"},
    ]
    agent = SpyAIAgent(completed_result(messages=messages))

    outputs = list(UpstreamAIAgentAdapter(agent).run(agent_turn, history))

    tool_events = [output for output in outputs if output.event_type == "tool_activity"]
    assert [(event.data["kind"], event.tool_call_id) for event in tool_events] == [
        ("tool_call", "call_42"),
        ("tool_result", "call_42"),
    ]
    assert tool_events[0].data["tool_call"]["function"]["name"] == "web_search"
    assert tool_events[1].data["tool_result"] == "found it"


def test_adapter_does_not_repeat_final_text_already_streamed(agent_turn):
    from hermes_personal.orchestration.upstream_agent import UpstreamAIAgentAdapter

    agent = SpyAIAgent(
        completed_result(final_response="one two"),
        on_run=lambda callback: (callback("one "), callback("two")),
    )

    outputs = list(UpstreamAIAgentAdapter(agent).run(agent_turn, ()))

    assert [(output.event_type, output.data.get("text")) for output in outputs] == [
        ("text_delta", "one "),
        ("text_delta", "two"),
        ("completed", None),
    ]


def test_adapter_raises_for_malformed_result_and_upstream_exception(agent_turn):
    from hermes_personal.orchestration.upstream_agent import UpstreamAIAgentAdapter

    malformed = SpyAIAgent({"final_response": "missing canonical fields"})
    with pytest.raises(ValueError, match="malformed upstream result"):
        list(UpstreamAIAgentAdapter(malformed).run(agent_turn, ()))

    class ExplodingAgent:
        def run_conversation(self, **kwargs):
            raise RuntimeError("upstream unavailable")

    with pytest.raises(RuntimeError, match="upstream unavailable"):
        list(UpstreamAIAgentAdapter(ExplodingAgent()).run(agent_turn, ()))


def test_adapter_emits_one_failed_terminal_for_canonical_failure(agent_turn):
    from hermes_personal.orchestration.upstream_agent import UpstreamAIAgentAdapter

    result = completed_result(final_response="cannot continue")
    result.update(
        completed=False,
        failed=True,
        error="database locked",
        failure_reason="session_persistence_failed:locked",
    )
    outputs = list(UpstreamAIAgentAdapter(SpyAIAgent(result)).run(agent_turn, ()))

    assert [output.event_type for output in outputs] == ["text_delta", "failed"]
    assert outputs[-1].data["error"] == "database locked"
    assert outputs[-1].data["failure_reason"] == "session_persistence_failed:locked"


def test_adapter_trusts_only_matching_upstream_workflow(agent_turn):
    from hermes_personal.orchestration import UpstreamAIAgentAdapter

    request_with_workflow = replace(agent_turn, workflow_id="wf_7")
    messages = [
        {
            "role": "assistant",
            "tool_calls": [{"id": "call_7", "function": {"name": "lookup"}}],
        }
    ]
    untrusted = completed_result(messages=messages)
    untrusted["workflow_id"] = "wf_other"

    untrusted_outputs = list(
        UpstreamAIAgentAdapter(SpyAIAgent(untrusted)).run(request_with_workflow, ())
    )

    assert {output.workflow_id for output in untrusted_outputs} == {None}

    trusted = completed_result(messages=messages)
    trusted["workflow_id"] = "wf_7"
    trusted_outputs = list(
        UpstreamAIAgentAdapter(SpyAIAgent(trusted)).run(request_with_workflow, ())
    )

    assert [
        output.workflow_id
        for output in trusted_outputs
        if output.event_type != "text_delta"
    ] == ["wf_7", "wf_7"]


def test_adapter_normalizes_interrupted_turn_to_one_failed_terminal(agent_turn):
    from hermes_personal.orchestration import UpstreamAIAgentAdapter

    result = completed_result(final_response="")
    result.update(completed=False, failed=False, interrupted=True)

    outputs = list(UpstreamAIAgentAdapter(SpyAIAgent(result)).run(agent_turn, ()))

    assert [output.event_type for output in outputs] == ["failed"]
    assert outputs[0].data["interrupted"] is True


@pytest.mark.parametrize(
    ("result", "terminal_type"),
    [
        (
            {"final_response": "early", "messages": [], "completed": True},
            "completed",
        ),
        (
            {
                "final_response": "partial",
                "messages": [],
                "completed": False,
                "partial": True,
            },
            "failed",
        ),
        (
            {
                "final_response": "interrupted",
                "messages": [],
                "completed": False,
                "interrupted": True,
            },
            "failed",
        ),
    ],
)
def test_adapter_accepts_public_early_return_shapes_with_optional_flags(
    agent_turn, result, terminal_type
):
    from hermes_personal.orchestration import UpstreamAIAgentAdapter

    outputs = list(UpstreamAIAgentAdapter(SpyAIAgent(result)).run(agent_turn, ()))

    terminals = [output for output in outputs if output.event_type in {"completed", "failed"}]
    assert [output.event_type for output in terminals] == [terminal_type]
    assert terminals[0].data["failed"] is False
    assert terminals[0].data["interrupted"] is result.get("interrupted", False)
    assert terminals[0].data.get("partial") is result.get("partial")


def test_adapter_drops_post_close_deltas_and_bounds_queue_retention(
    agent_turn, monkeypatch
):
    import hermes_personal.orchestration.upstream_agent as upstream_agent

    class TrackingQueue(StdlibQueue):
        instances: list[TrackingQueue] = []

        def __init__(self, maxsize: int = 0) -> None:
            super().__init__(maxsize=maxsize)
            self.__class__.instances.append(self)

    class ManyDeltaAgent:
        def __init__(self) -> None:
            self.release = threading.Event()
            self.completed = threading.Event()

        def run_conversation(self, **kwargs: Any) -> Mapping[str, Any]:
            callback = kwargs["stream_callback"]
            callback("first")
            self.release.wait(1)
            for _ in range(1_000):
                callback("after close")
            self.completed.set()
            return {"final_response": "", "messages": [], "completed": True}

    monkeypatch.setattr(upstream_agent, "Queue", TrackingQueue)
    agent = ManyDeltaAgent()
    outputs = upstream_agent.UpstreamAIAgentAdapter(agent).run(agent_turn, ())

    assert next(outputs).data == {"text": "first"}
    assert TrackingQueue.instances[0].maxsize > 0
    outputs.close()
    agent.release.set()

    assert agent.completed.wait(1)
    assert TrackingQueue.instances[0].qsize() <= TrackingQueue.instances[0].maxsize
