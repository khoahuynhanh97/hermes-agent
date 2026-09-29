from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from hermes_personal.product_video.creative.model_adapter import (
    HermesStructuredCreativeModel,
)
from hermes_personal.product_video.creative.prompts import CREATIVE_BRIEF_V2_SCHEMA


def _response(content: str, *, model: str = "gemini-test", tokens: int = 17) -> Any:
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=tokens),
    )


def test_adapter_uses_host_auxiliary_route_and_json_schema() -> None:
    calls: list[dict[str, Any]] = []

    def caller(**kwargs: Any) -> Any:
        calls.append(kwargs)
        kwargs["route_info"].update(provider="vertex", model="configured-model")
        return _response('{"ok": true}')

    result = HermesStructuredCreativeModel(caller=caller).generate_json(
        system_prompt="grounded system",
        user_prompt="dossier",
        schema_name="creative-brief-v2",
        json_schema={"type": "object"},
        temperature=0.4,
    )

    assert result.parsed == {"ok": True}
    assert result.provider == "vertex"
    assert result.model == "gemini-test"
    assert result.total_tokens == 17
    assert calls[0]["task"] == "product_video_creative"
    assert calls[0]["extra_body"]["response_format"]["type"] == "json_schema"
    assert calls[0]["extra_body"]["response_format"]["json_schema"]["name"] == (
        "creative-brief-v2"
    )


def test_adapter_preserves_invalid_raw_response_for_generator_repair() -> None:
    result = HermesStructuredCreativeModel(
        caller=lambda **_: _response("```json\n{truncated\n```")
    ).generate_json(
        system_prompt="system",
        user_prompt="prompt",
        schema_name="script-scene-plan-v2",
        json_schema={"type": "object"},
        temperature=0.3,
    )

    assert result.parsed == {}
    assert result.raw_text == "```json\n{truncated\n```"
    assert result.parse_error


def test_vertex_compatible_brief_schema_declares_every_required_property() -> None:
    properties = CREATIVE_BRIEF_V2_SCHEMA["properties"]
    assert all(name in properties for name in CREATIVE_BRIEF_V2_SCHEMA["required"])
