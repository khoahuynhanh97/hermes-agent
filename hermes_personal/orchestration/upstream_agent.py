from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from queue import Full, Queue
from threading import Event, Thread
from typing import Any, Callable, Protocol

from hermes_personal.contracts import AgentTurnRequest

from .ports import AgentOutput


class PublicAIAgent(Protocol):
    def run_conversation(
        self,
        *,
        user_message: Any,
        conversation_history: list[Mapping[str, Any]],
        task_id: str,
        stream_callback: Callable[[str | None], None],
        persist_user_message: Any,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class _TextDelta:
    text: str


@dataclass(frozen=True)
class _Result:
    value: Any


@dataclass(frozen=True)
class _Exception:
    value: BaseException


_WORKER_FINISHED = object()
_REQUIRED_RESULT_FIELDS = frozenset({"final_response", "messages", "completed"})
_EVENT_QUEUE_MAXSIZE = 32


class UpstreamAIAgentAdapter:
    """Convert the public upstream turn result into the canonical agent port."""

    def __init__(self, agent: PublicAIAgent) -> None:
        self._agent = agent

    def run(
        self,
        request: AgentTurnRequest,
        history: tuple[Mapping[str, Any], ...],
    ) -> Iterator[AgentOutput]:
        events: Queue[_TextDelta | _Result | _Exception | object] = Queue(
            maxsize=_EVENT_QUEUE_MAXSIZE
        )
        closed = Event()
        streamed_text: list[str] = []

        def stream_callback(delta: str | None) -> None:
            if isinstance(delta, str) and delta:
                _enqueue_while_open(events, _TextDelta(delta), closed)

        def invoke() -> None:
            try:
                result = self._agent.run_conversation(
                    user_message=request.message,
                    conversation_history=list(history),
                    task_id=request.turn_id,
                    stream_callback=stream_callback,
                    persist_user_message=request.message,
                )
            except BaseException as error:
                _enqueue_while_open(events, _Exception(error), closed)
            else:
                _enqueue_while_open(events, _Result(result), closed)
            finally:
                _enqueue_while_open(events, _WORKER_FINISHED, closed)

        worker = Thread(target=invoke, name="hermes-upstream-agent", daemon=True)
        worker.start()

        try:
            while True:
                item = events.get()
                if isinstance(item, _TextDelta):
                    streamed_text.append(item.text)
                    yield AgentOutput("text_delta", {"text": item.text})
                    continue
                if isinstance(item, _Exception):
                    raise item.value
                if isinstance(item, _Result):
                    yield from self._outputs_from_result(
                        item.value, request, history, streamed_text
                    )
                    continue
                if item is _WORKER_FINISHED:
                    return
                raise RuntimeError("unexpected upstream adapter worker event")
        finally:
            closed.set()

    @staticmethod
    def _outputs_from_result(
        result: Any,
        request: AgentTurnRequest,
        history: tuple[Mapping[str, Any], ...],
        streamed_text: list[str],
    ) -> Iterator[AgentOutput]:
        result_mapping = _validate_result(result)
        workflow_id = _trusted_workflow_id(result_mapping, request)

        yield from _new_tool_outputs(result_mapping["messages"], history, workflow_id)

        final_response = result_mapping["final_response"]
        if final_response:
            remaining_text = _remaining_final_text(final_response, "".join(streamed_text))
            if remaining_text:
                yield AgentOutput("text_delta", {"text": remaining_text})

        terminal_type = (
            "completed"
            if result_mapping["completed"] and not result_mapping["failed"]
            else "failed"
        )
        terminal_data = dict(result_mapping)
        raw_msgs = result_mapping.get("messages", [])
        if len(raw_msgs) >= len(history) and list(raw_msgs[: len(history)]) == list(history):
            turn_messages = raw_msgs[len(history) :]
        else:
            turn_messages = raw_msgs
        terminal_data["turn_messages"] = turn_messages
        terminal_data["messages"] = turn_messages
        yield AgentOutput(terminal_type, terminal_data, workflow_id=workflow_id)


def _validate_result(result: Any) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("malformed upstream result: expected a mapping")

    missing = sorted(_REQUIRED_RESULT_FIELDS - result.keys())
    if missing:
        raise ValueError(f"malformed upstream result: missing {', '.join(missing)}")
    if not isinstance(result["messages"], list):
        raise ValueError("malformed upstream result: messages must be a list")
    if not isinstance(result["completed"], bool):
        raise ValueError("malformed upstream result: completed must be a bool")
    normalized = dict(result)
    for field_name in ("failed", "interrupted"):
        value = normalized.get(field_name, False)
        if not isinstance(value, bool):
            raise ValueError(f"malformed upstream result: {field_name} must be a bool")
        normalized[field_name] = value
    if normalized["final_response"] is not None and not isinstance(
        normalized["final_response"], str
    ):
        raise ValueError("malformed upstream result: final_response must be text or null")
    for message in normalized["messages"]:
        if not isinstance(message, Mapping):
            raise ValueError("malformed upstream result: messages must contain mappings")
    return normalized


def _enqueue_while_open(
    events: Queue[_TextDelta | _Result | _Exception | object],
    item: _TextDelta | _Result | _Exception | object,
    closed: Event,
) -> bool:
    while not closed.is_set():
        try:
            events.put(item, timeout=0.05)
        except Full:
            continue
        return True
    return False


def _trusted_workflow_id(
    result: Mapping[str, Any], request: AgentTurnRequest
) -> str | None:
    workflow_id = result.get("workflow_id")
    if isinstance(workflow_id, str) and workflow_id == request.workflow_id:
        return workflow_id
    return None


def _remaining_final_text(final_response: str, streamed: str) -> str:
    if not streamed:
        return final_response
    if final_response.startswith(streamed):
        return final_response[len(streamed) :]
    if final_response in streamed:
        return ""
    return final_response


def _new_tool_outputs(
    messages: list[Mapping[str, Any]],
    history: tuple[Mapping[str, Any], ...],
    workflow_id: str | None,
) -> Iterator[AgentOutput]:
    known_call_ids = _tool_call_ids(history)
    known_result_ids = _tool_result_ids(history)
    emitted_call_ids: set[str] = set()
    emitted_result_ids: set[str] = set()

    for message in messages:
        role = message.get("role")
        if role == "assistant":
            tool_calls = message.get("tool_calls")
            if tool_calls is None:
                continue
            if not isinstance(tool_calls, (list, tuple)):
                raise ValueError("malformed upstream result: tool_calls must be a list")
            for tool_call in tool_calls:
                if not isinstance(tool_call, Mapping):
                    raise ValueError("malformed upstream result: tool call must be a mapping")
                tool_call_id = _tool_call_id(tool_call, "tool call")
                if tool_call_id in known_call_ids or tool_call_id in emitted_call_ids:
                    continue
                emitted_call_ids.add(tool_call_id)
                data: dict[str, Any] = {"kind": "tool_call", "tool_call": tool_call}
                function = tool_call.get("function")
                if isinstance(function, Mapping) and isinstance(function.get("name"), str):
                    data["tool_name"] = function["name"]
                yield AgentOutput(
                    "tool_activity",
                    data,
                    workflow_id=workflow_id,
                    tool_call_id=tool_call_id,
                )
        elif role == "tool":
            tool_call_id = _tool_call_id(message, "tool result")
            if tool_call_id in known_result_ids or tool_call_id in emitted_result_ids:
                continue
            emitted_result_ids.add(tool_call_id)
            yield AgentOutput(
                "tool_activity",
                {
                    "kind": "tool_result",
                    "tool_result": message.get("content"),
                    "message": message,
                },
                workflow_id=workflow_id,
                tool_call_id=tool_call_id,
            )


def _tool_call_ids(messages: tuple[Mapping[str, Any], ...]) -> set[str]:
    identifiers: set[str] = set()
    for message in messages:
        if message.get("role") != "assistant":
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, (list, tuple)):
            continue
        for tool_call in tool_calls:
            if isinstance(tool_call, Mapping):
                tool_call_id = tool_call.get("id")
                if isinstance(tool_call_id, str) and tool_call_id:
                    identifiers.add(tool_call_id)
    return identifiers


def _tool_result_ids(messages: tuple[Mapping[str, Any], ...]) -> set[str]:
    return {
        message["tool_call_id"]
        for message in messages
        if message.get("role") == "tool"
        and isinstance(message.get("tool_call_id"), str)
        and message["tool_call_id"]
    }


def _tool_call_id(message: Mapping[str, Any], label: str) -> str:
    value = message.get("id") if label == "tool call" else message.get("tool_call_id")
    if not isinstance(value, str) or not value:
        raise ValueError(f"malformed upstream result: {label} is missing an id")
    return value
