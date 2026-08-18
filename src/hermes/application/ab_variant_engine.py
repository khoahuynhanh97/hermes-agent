"""A/B Hook Variant Generation Engine.

Generates 3 distinct hook variants (Curiosity, Problem-Pain, Shocking Benefit)
from a single product, each with its own creative brief and scene plan.
"""
from __future__ import annotations

from typing import Any

from hermes.domain.video_factory import (
    CreativeBrief, Scene, ScenePlan, HookVariant, ABVariantSet,
    new_id,
)

HOOK_TEMPLATES: dict[str, dict[str, Any]] = {
    "curiosity_gap": {
        "label": "Curiosity Hook",
        "description": "Opens with a mystery or surprising fact",
        "angle": "Problem-Agitate-Solve",
        "scene_titles": [
            "Mystery Reveal",
            "Feature Discovery",
            "Deep Dive",
            "Solution & CTA",
        ],
    },
    "problem_agitate": {
        "label": "Problem-Pain Hook",
        "description": "Starts with pain point, agitates, then solves",
        "angle": "Hook-Feature-Benefit",
        "scene_titles": [
            "Pain Point",
            "Agitate Problem",
            "Product Solution",
            "CTA & Offer",
        ],
    },
    "shocking_benefit": {
        "label": "Shocking Benefit Hook",
        "description": "Opens with the most impressive stat or benefit",
        "angle": "Before-After",
        "scene_titles": [
            "Shocking Stat",
            "Before State",
            "After Transformation",
            "CTA & Social Proof",
        ],
    },
}


def _build_curiosity_brief(
    product_name: str, platform: str, duration: int,
) -> CreativeBrief:
    return CreativeBrief(
        objective=(
            f"Tease a surprising fact about {product_name} to hook viewers. "
            "Build curiosity in the first 3 seconds, reveal features in the middle, "
            "close with a compelling CTA."
        ),
        target_audience=f"Tech enthusiasts and curious shoppers on {platform}",
        core_message=f"Discover the unexpected side of {product_name} that nobody talks about",
        tone="Mysterious, intriguing, confident",
        pace="Slow build, fast payoff",
        cta=f"Find out why everyone is talking about {product_name}",
        content_blocks=("Mystery Hook", "Surprising Feature", "Deep Dive", "CTA Reveal"),
        platform=platform,
        aspect_ratio="9:16",
        target_duration_seconds=duration,
    )


def _build_problem_pain_brief(
    product_name: str, platform: str, duration: int,
) -> CreativeBrief:
    return CreativeBrief(
        objective=(
            f"Agitate a real pain point, then present {product_name} as the solution. "
            "Emotional hook in the first 3 seconds, problem escalation, product reveal, CTA."
        ),
        target_audience=f"Frustrated users seeking solutions on {platform}",
        core_message=f"{product_name} eliminates the #1 problem you face every day",
        tone="Empathetic, urgent, empowering",
        pace="Tense opening, relief middle, confident close",
        cta=f"Stop struggling. Get {product_name} now",
        content_blocks=("Pain Hook", "Problem Escalation", "Product Solution", "CTA"),
        platform=platform,
        aspect_ratio="9:16",
        target_duration_seconds=duration,
    )


def _build_shocking_benefit_brief(
    product_name: str, platform: str, duration: int,
) -> CreativeBrief:
    return CreativeBrief(
        objective=(
            f"Lead with the single most impressive stat or benefit of {product_name}. "
            "Shocking opener, before/after contrast, social proof CTA."
        ),
        target_audience=f"Results-driven shoppers on {platform}",
        core_message=f"The one stat about {product_name} that will blow your mind",
        tone="Bold, data-driven, confident",
        pace="Impact opening, evidence middle, urgency close",
        cta=f"See the results for yourself: get {product_name}",
        content_blocks=("Shocking Stat Hook", "Before State", "After Transformation", "CTA & Proof"),
        platform=platform,
        aspect_ratio="9:16",
        target_duration_seconds=duration,
    )


_BRIEF_BUILDERS = {
    "curiosity_gap": _build_curiosity_brief,
    "problem_agitate": _build_problem_pain_brief,
    "shocking_benefit": _build_shocking_benefit_brief,
}


def _build_scene_plan(
    hook_key: str, product_name: str, duration: int,
) -> ScenePlan:
    template = HOOK_TEMPLATES[hook_key]
    titles = template["scene_titles"]
    n = len(titles)
    base_dur = duration // n
    remainder = duration - base_dur * n
    scenes = []
    for i, title in enumerate(titles):
        dur = base_dur + (1 if i < remainder else 0)
        scenes.append(
            Scene(
                scene_id=f"variant_{hook_key}_s{i + 1}",
                order=i + 1,
                title=title,
                objective=f"Scene {i + 1} of {template['label']}: {title}",
                content=f"{product_name} - {title}",
                main_action=title,
                duration_seconds=dur,
                context=f"{template['angle']} angle",
                camera_intention="Dynamic vertical 9:16 framing",
            )
        )
    return ScenePlan(scenes=tuple(scenes))


class ABVariantEngine:
    """Generates 3 A/B hook variants from a product and base prompt."""

    def generate_variants(
        self,
        product_name: str,
        base_prompt: str,
        platform: str = "TikTok",
        duration_seconds: int = 30,
    ) -> ABVariantSet:
        """Generate 3 hook variants from a product."""
        variants = []
        for hook_key, template in HOOK_TEMPLATES.items():
            brief = _BRIEF_BUILDERS[hook_key](product_name, platform, duration_seconds)
            scene_plan = _build_scene_plan(hook_key, product_name, duration_seconds)
            variant = HookVariant(
                variant_id=new_id("abv"),
                variant_label=template["label"],
                hook_angle=template["angle"],
                creative_brief=brief,
                scene_plan=scene_plan,
            )
            variants.append(variant)
        return ABVariantSet(variants=tuple(variants))

    def select_winner(
        self,
        variant_set: ABVariantSet,
        variant_id: str,
    ) -> ABVariantSet:
        """Mark a variant as the winner."""
        ids = {v.variant_id for v in variant_set.variants}
        if variant_id not in ids:
            raise ValueError(f"VARIANT_NOT_FOUND: {variant_id}")
        return ABVariantSet(
            variants=variant_set.variants,
            selected_variant_id=variant_id,
        )
