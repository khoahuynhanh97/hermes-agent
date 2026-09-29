"""Single-model implementation of the grounded creative generation boundary."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

from .contracts import (
    CreativeBriefV2,
    GenerationProvenance,
    ResearchDossier,
    ScriptScenePlanV2,
)
from .ports import StructuredCreativeModel, StructuredModelResult
from .prompts import (
    COMMON_GROUNDED_SYSTEM_PROMPT,
    CREATIVE_BRIEF_V2_SCHEMA,
    CREATIVE_DIRECTION_PROMPT_V2,
    SCRIPT_SCENE_PLAN_PROMPT_V2,
    SCRIPT_SCENE_PLAN_V2_SCHEMA,
)
from .validation import validate_brief, validate_script


class StructuredGenerationError(RuntimeError):
    pass


ArtifactT = TypeVar("ArtifactT")


class SingleModelCreativeGenerator:
    def __init__(self, model: StructuredCreativeModel) -> None:
        self.model = model

    @staticmethod
    def _provenance(
        result: StructuredModelResult,
        *,
        prompt_version: str,
        input_digests: tuple[str, ...],
    ) -> GenerationProvenance:
        return GenerationProvenance(
            prompt_version=prompt_version,
            provider=result.provider,
            model=result.model,
            input_digests=input_digests,
            raw_response=result.raw_text,
            parse_error=result.parse_error,
            token_usage=result.total_tokens,
        )

    def _generate(
        self,
        *,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
        temperature: float,
        parser: Callable[[dict[str, Any], StructuredModelResult], ArtifactT],
    ) -> ArtifactT:
        current_prompt = user_prompt
        errors: list[str] = []
        for attempt in range(2):
            result = self.model.generate_json(
                system_prompt=COMMON_GROUNDED_SYSTEM_PROMPT,
                user_prompt=current_prompt,
                schema_name=schema_name,
                json_schema=json_schema,
                temperature=temperature,
            )
            try:
                if not isinstance(result.parsed, dict):
                    detail = f": {result.parse_error}" if result.parse_error else ""
                    raise ValueError(f"structured response must be a JSON object{detail}")
                return parser(result.parsed, result)
            except (KeyError, TypeError, ValueError) as exc:
                diagnostic = str(exc)
                if schema_name == "creative-brief-v2" and isinstance(result.parsed, dict):
                    reasons = result.parsed.get("reason_to_believe", "<missing>")
                    diagnostic += f" (reason_to_believe={str(reasons)[:500]})"
                errors.append(diagnostic)
                if attempt == 1:
                    break
                current_prompt = (
                    f"{user_prompt}\n\nVALIDATION ERRORS\n- {exc}\n"
                    f"INVALID RESPONSE\n{result.raw_text}\n"
                    "Return a corrected JSON object only."
                )
        raise StructuredGenerationError(
            f"two invalid responses for {schema_name}: {' | '.join(errors)}"
        )

    def create_direction(self, dossier: ResearchDossier) -> CreativeBriefV2:
        if not dossier.verified_claims:
            raise StructuredGenerationError(
                "creative brief requires at least one claim with verified source evidence"
            )
        prompt = CREATIVE_DIRECTION_PROMPT_V2.format(
            research_dossier_json=dossier.to_json()
        )

        def parse(data: dict[str, Any], result: StructuredModelResult) -> CreativeBriefV2:
            data = dict(data)
            data["dossier_digest"] = dossier.digest()
            data["prompt_version"] = "creative-direction-v2.3"
            brief = CreativeBriefV2.from_dict(
                data,
                provenance=self._provenance(
                    result,
                    prompt_version="creative-direction-v2.3",
                    input_digests=(dossier.digest(),),
                ),
            )
            validate_brief(dossier, brief)
            return brief

        return self._generate(
            user_prompt=prompt,
            schema_name="creative-brief-v2",
            json_schema=CREATIVE_BRIEF_V2_SCHEMA,
            temperature=0.4,
            parser=parse,
        )

    def create_script(
        self,
        dossier: ResearchDossier,
        brief: CreativeBriefV2,
        *,
        revision_feedback: str = "",
    ) -> ScriptScenePlanV2:
        prompt = SCRIPT_SCENE_PLAN_PROMPT_V2.format(
            research_dossier_json=dossier.to_json(),
            creative_brief_json=json.dumps(brief.to_dict(), ensure_ascii=False, sort_keys=True),
        )
        if revision_feedback.strip():
            prompt += (
                "\n\nOPERATOR REVISION FEEDBACK\n"
                f"{revision_feedback.strip()}\n"
                "Regenerate the complete plan. Keep every scene grounded in verified claims."
            )

        def parse(data: dict[str, Any], result: StructuredModelResult) -> ScriptScenePlanV2:
            data = dict(data)
            data["schema_version"] = "script-scene-plan-v2"
            data["brief_digest"] = brief.digest()
            data["prompt_version"] = "script-scene-plan-v3"
            script = ScriptScenePlanV2.from_dict(
                data,
                provenance=self._provenance(
                    result,
                    prompt_version="script-scene-plan-v3",
                    input_digests=(dossier.digest(), brief.digest()),
                ),
            )
            validate_script(dossier, brief, script)
            return script

        return self._generate(
            user_prompt=prompt,
            schema_name="script-scene-plan-v2",
            json_schema=SCRIPT_SCENE_PLAN_V2_SCHEMA,
            temperature=0.3,
            parser=parse,
        )
