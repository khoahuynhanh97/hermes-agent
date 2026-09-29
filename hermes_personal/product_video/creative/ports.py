"""Model/provider boundaries for Product Video creative generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .contracts import CreativeBriefV2, ResearchDossier, ScriptScenePlanV2


@dataclass(frozen=True)
class StructuredModelResult:
    parsed: dict[str, Any] | list[dict[str, Any]]
    raw_text: str
    provider: str
    model: str
    total_tokens: int = 0
    parse_error: str = ""


class StructuredCreativeModel(Protocol):
    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: Mapping[str, object],
        temperature: float,
    ) -> StructuredModelResult:
        raise NotImplementedError


class CreativeGenerationPort(Protocol):
    def create_direction(self, dossier: ResearchDossier) -> CreativeBriefV2:
        raise NotImplementedError

    def create_script(
        self,
        dossier: ResearchDossier,
        brief: CreativeBriefV2,
    ) -> ScriptScenePlanV2:
        raise NotImplementedError
