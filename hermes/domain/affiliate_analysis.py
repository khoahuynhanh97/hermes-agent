"""Spec-compliant affiliate analysis output schema.

Mirrors the ``AffiliateAnalysisOutput`` contract from the
2026-08-02 design spec: TikTok 3-act script (Hook / Body / CTA),
distinct Flux-style image prompt and Runway-style video prompt,
plus explicit USP and pain-point lists produced from the
product metadata and any cached ``web_documents`` markdown.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TikTokScript:
    hook: str
    body: str
    cta: str


@dataclass(frozen=True)
class VisualPrompts:
    image_prompt: str
    video_prompt: str


@dataclass(frozen=True)
class AffiliateAnalysis:
    """Layer-3 structured AI output for a single affiliate product.

    All fields are required. ``target_audience`` is the same
    Vietnamese audience description the spec uses; ``usp_list`` and
    ``pain_points`` are deliberately small lists for downstream
    marketing copy. ``tiktok_script`` and ``visual_prompts`` follow
    the exact 3-act / dual-prompt shape from the design document.
    """

    analysis_id: str
    owner_user_id: str
    product_id: str
    run_id: str
    usp_list: tuple[str, ...]
    pain_points: tuple[str, ...]
    target_audience: str
    tiktok_script: TikTokScript
    visual_prompts: VisualPrompts
    fallback_used: bool
    created_at: str


VALID_USP_KEYS = ("usp_list",)
VALID_PAIN_KEYS = ("pain_points",)
REQUIRED_SCRIPT_KEYS = ("hook", "body", "cta")
REQUIRED_VISUAL_KEYS = ("image_prompt", "video_prompt")
