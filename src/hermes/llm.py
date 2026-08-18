from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from hermes.application.core.llm_gateway import complete as gateway_complete


TEXT_TASKS = {
    "chat",
    "summarize",
    "learning",
    "analysis",
    "deep_analysis",
    "code",
    "structured_extraction",
    "ideas",
    "script",
}


class HermesLLMError(RuntimeError):
    pass


class CapabilityMismatchError(HermesLLMError):
    pass


class StructuredOutputError(HermesLLMError):
    pass


class HermesLLMGateway:
    """Typed Hermes-facing wrapper around the shared OpenAI-compatible endpoint."""

    def __init__(self, complete_fn: Callable[..., str] | None = None):
        self._complete = complete_fn or gateway_complete

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        task_type: str = "chat",
        max_tokens: int = 4096,
    ) -> str:
        normalized_task = (task_type or "chat").strip().lower()
        if normalized_task not in TEXT_TASKS:
            raise CapabilityMismatchError(
                f"Task '{normalized_task}' requires a dedicated capability adapter"
            )
        return self._complete(
            prompt=prompt,
            system=system,
            task_type=normalized_task,
            max_tokens=max_tokens,
        )

    def structured(
        self,
        prompt: str,
        *,
        schema: dict[str, type],
        system: str = "",
        task_type: str = "structured_extraction",
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        raw = self.complete(
            prompt,
            system=system,
            task_type=task_type,
            max_tokens=max_tokens,
        )
        try:
            value = self._decode_json_object(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StructuredOutputError("Model response is not a valid JSON object") from exc
        for field, expected_type in schema.items():
            if field not in value:
                raise StructuredOutputError(f"Structured response is missing '{field}'")
            if not isinstance(value[field], expected_type):
                raise StructuredOutputError(
                    f"Structured field '{field}' must be {expected_type.__name__}"
                )
        return value

    @staticmethod
    def _decode_json_object(raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
        start = text.find("{")
        if start < 0:
            raise ValueError("No JSON object found")
        value, _end = json.JSONDecoder().raw_decode(text[start:])
        if not isinstance(value, dict):
            raise TypeError("JSON value is not an object")
        return value
