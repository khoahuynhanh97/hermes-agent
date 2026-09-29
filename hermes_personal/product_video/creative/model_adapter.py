"""Host-owned structured LLM adapter for Product Video creative generation."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Mapping

from .ports import StructuredModelResult


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _usage_total(response: Any) -> int:
    usage = getattr(response, "usage", None)
    if isinstance(usage, dict):
        return int(usage.get("total_tokens") or 0)
    return int(getattr(usage, "total_tokens", 0) or 0)


class HermesStructuredCreativeModel:
    """Route creative JSON calls through Hermes' central provider resolver.

    This is intentionally an edge adapter rather than a new model tool. It
    inherits configured credentials, routing, retries and provider fallbacks
    from ``agent.auxiliary_client`` while keeping the creative core testable.
    """

    def __init__(
        self,
        *,
        caller: Callable[..., Any] | None = None,
        task: str = "product_video_creative",
        provider: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        max_tokens: int = 8192,
        main_runtime: dict[str, Any] | None = None,
    ) -> None:
        self._caller = caller
        self.task = task
        self.provider = provider
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.main_runtime = main_runtime

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: Mapping[str, object],
        temperature: float,
    ) -> StructuredModelResult:
        caller = self._caller
        if caller is None:
            from agent.auxiliary_client import call_llm

            caller = call_llm

        route_info: dict[str, str] = {}
        response = caller(
            task=self.task,
            provider=self.provider,
            model=self.model,
            main_runtime=self.main_runtime,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            extra_body={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "schema": dict(json_schema),
                        "strict": False,
                    },
                }
            },
            route_info=route_info,
        )

        from agent.auxiliary_client import extract_content_or_reasoning

        raw_text = extract_content_or_reasoning(response)
        parse_error = ""
        parsed: dict[str, Any] = {}
        try:
            candidate = json.loads(_strip_json_fence(raw_text))
            if not isinstance(candidate, dict):
                raise ValueError("structured response must be a JSON object")
            parsed = candidate
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            parse_error = str(exc)

        response_model = str(getattr(response, "model", "") or "").strip()
        resolved_provider = (
            route_info.get("provider") or self.provider or "auto"
        )
        resolved_model = response_model or route_info.get("model") or self.model or "default"
        return StructuredModelResult(
            parsed=parsed,
            raw_text=raw_text,
            provider=resolved_provider,
            model=resolved_model,
            total_tokens=_usage_total(response),
            parse_error=parse_error,
        )
