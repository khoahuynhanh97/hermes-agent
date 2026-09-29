from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from hermes_personal.product_video.creative.contracts import (
    CreativeBriefV2,
    EligibleAsset,
    EvidenceClaim,
    ProductIdentityV2,
    ResearchDossier,
)
from hermes_personal.product_video.creative.generator import (
    SingleModelCreativeGenerator,
    StructuredGenerationError,
)
from hermes_personal.product_video.creative.ports import StructuredModelResult


def _dossier() -> ResearchDossier:
    return ResearchDossier.create(
        workflow_id="pv-generator-test",
        product_identity=ProductIdentityV2(
            brand="Baseus",
            model="Bowie WM02",
            display_name="Baseus Bowie WM02",
        ),
        verified_claims=(
            EvidenceClaim("claim-01", "Tai nghe đi kèm hộp sạc", ("evidence-01",)),
        ),
        eligible_assets=(
            EligibleAsset("asset-1", "C:/media/one.jpg", "1" * 64, "iqc-1"),
            EligibleAsset("asset-2", "C:/media/two.jpg", "2" * 64, "iqc-1"),
        ),
        pain_points=("Khó cất tai nghe nhanh khi di chuyển",),
        use_cases=("Rời bàn làm việc",),
    )


def _valid_brief(dossier: ResearchDossier) -> dict[str, Any]:
    return {
        "schema_version": "creative-brief-v2",
        "audience": {
            "segment": "Người thường xuyên mang tai nghe khi di chuyển",
            "situation": "Rời bàn làm việc",
            "desired_outcome": "Cất tai nghe nhanh và gọn",
        },
        "consumer_insight": "Tai nghe chỉ tiện khi lấy ra và cất lại không làm gián đoạn việc di chuyển",
        "problem": "Tai nghe dễ bị bỏ quên nếu việc cất lại mất thời gian",
        "creative_angle": "Theo chân một lần cất tai nghe trước khi rời bàn",
        "hook": "Bạn mất bao lâu để cất tai nghe trước khi đi?",
        "promise": "Cho thấy thao tác cất tai nghe vào hộp trong một tình huống thực tế",
        "reason_to_believe": [
            {"text": "Tai nghe đi kèm hộp sạc", "evidence_refs": ["claim-01"]}
        ],
        "tone": "Đời thường, nhanh và rõ",
        "story_archetype": "problem_solution_demo",
        "cta": "Xem thêm thông tin sản phẩm.",
        "restrictions": ["Không đưa thông tin khuyến mãi"],
        "target_duration_seconds": 18,
        "prompt_version": "creative-direction-v2",
        "dossier_digest": dossier.digest(),
    }


@dataclass
class _Request:
    system_prompt: str
    user_prompt: str
    schema_name: str


class _FakeModel:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.requests: list[_Request] = []

    def generate_json(self, **kwargs: Any) -> StructuredModelResult:
        self.requests.append(
            _Request(
                system_prompt=kwargs["system_prompt"],
                user_prompt=kwargs["user_prompt"],
                schema_name=kwargs["schema_name"],
            )
        )
        parsed = self.responses.pop(0)
        return StructuredModelResult(
            parsed=parsed,
            raw_text=str(parsed),
            provider="fake-provider",
            model="fake-model",
            total_tokens=100,
        )


def test_direction_prompt_contains_dossier_and_grounding_rules() -> None:
    dossier = _dossier()
    model = _FakeModel([_valid_brief(dossier)])

    brief = SingleModelCreativeGenerator(model).create_direction(dossier)

    request = model.requests[0]
    assert dossier.product_identity.display_name in request.user_prompt
    assert "Every factual product claim" in request.system_prompt
    assert request.schema_name == "creative-brief-v2"
    assert brief.dossier_digest == dossier.digest()
    assert brief.provenance.model == "fake-model"
    assert CreativeBriefV2.from_dict(brief.to_dict()).digest() == brief.digest()


def test_generator_allows_one_repair_call_then_stops() -> None:
    dossier = _dossier()
    model = _FakeModel(
        [
            {"creative_angle": "missing required fields"},
            {"creative_angle": "still invalid"},
        ]
    )

    with pytest.raises(StructuredGenerationError, match="two invalid responses"):
        SingleModelCreativeGenerator(model).create_direction(dossier)

    assert len(model.requests) == 2
    assert "VALIDATION ERRORS" in model.requests[1].user_prompt


def test_generator_does_not_call_model_without_grounded_claims() -> None:
    dossier = _dossier()
    empty_dossier = ResearchDossier.create(
        workflow_id=dossier.workflow_id,
        product_identity=dossier.product_identity,
        verified_claims=(),
        eligible_assets=dossier.eligible_assets,
    )
    model = _FakeModel([])
    with pytest.raises(StructuredGenerationError, match="verified source evidence"):
        SingleModelCreativeGenerator(model).create_direction(empty_dossier)
    assert model.requests == []
