from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "relative_path",
    [
        ".agents/skills/hermes-personal-product-video-production/SKILL.md",
        "skills/video/hermes-personal-product-video-production/SKILL.md",
    ],
)
def test_product_video_skill_requires_ranked_references_and_controlled_recovery(
    relative_path: str,
) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8").casefold()

    for required in (
        "reference_rank",
        "product_identity_cues",
        "keyframe qc",
        "reselect_reference",
        "rewrite_prompt",
        "regenerate_keyframe",
        "seller/shop",
        "post-production",
    ):
        assert required.casefold() in text


@pytest.mark.parametrize(
    "relative_path",
    [
        ".agents/skills/hermes-personal-product-research/SKILL.md",
        "skills/research/hermes-personal-product-research/SKILL.md",
    ],
)
def test_product_research_skill_defines_reference_filtering_profile(
    relative_path: str,
) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8").casefold()

    for required in (
        "duplicate",
        "wrong variant",
        "screenshot",
        "collage",
        "watermark",
        "view_angle",
        "scene_suitability",
        "visible_details",
    ):
        assert required.casefold() in text
