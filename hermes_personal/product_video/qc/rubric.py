"""QC Rubrics and Prompt Templates for Multimodal Image & Video Evaluation."""

from __future__ import annotations

import json
from typing import Any


IMAGE_QC_SYSTEM_PROMPT = """You are a rigorous AI Quality Control inspector for e-commerce marketing media.
Your job is to inspect product images against a target product identity (Brand, Model, Key Features).
You MUST evaluate objectively and return strictly valid JSON matching the specified schema.
DO NOT assume or hallucinate features. If the image depicts a completely different product or wrong brand/model, flag it as a hard failure.
Reject source-store contamination: visible seller names, shop names, marketplace UI, watermarks, unrelated logos, price/rating badges, social handles, or shipping labels must not be accepted as clean render references."""


def build_image_qc_prompt(
    brand: str,
    model: str,
    variant: str = "",
    display_name: str = "",
    key_features: list[str] | None = None,
) -> str:
    features_str = ", ".join(key_features) if key_features else "None specified"
    return f"""Target Product Identity:
- Brand: {brand or "Unknown"}
- Model: {model or "Unknown"}
- Variant: {variant or "Standard"}
- Name: {display_name or f"{brand} {model}"}
- Key Features / Evidence: {features_str}

Evaluate the provided image according to this 100-point rubric:
1. Product Identity & Evidence (0 - 60 points):
   - Does this image clearly depict the target brand and model?
   - Are there conflicting branding, wrong model numbers, or mismatching product types?
   - If wrong brand/model/variant: hard_failure MUST be true, score for this section is 0.
   - If there is not enough visual detail to confirm or distinguish the model: mark verdict as "unknown".
   - If the image contains seller/shop/source branding, marketplace UI, watermarks, unrelated logos, price/rating badges, social handles, or prominent readable text unrelated to the product identity: hard_failure MUST be true.
2. Image Clarity & Quality (0 - 25 points):
   - Is the image sharp, well-lit, and in focus?
   - Is the product clearly visible without heavy occlusion, watermarks, or severe compression?
3. Reference Usability (0 - 15 points):
   - Can this image serve as a clean visual reference for AI video generation (Veo 3.1)?
   - Is the subject isolated or centered in a natural commercial setting?
   - Do not pass screenshots, shop cards, catalog tiles, or images where source/seller branding could be reproduced by the video model.
   - Penalize collages, banners, misleading angles, heavy occlusion, excessive text and crops that hide identity-critical details.

Reference Profile:
- Describe the view_angle and shot_type using concise visual terms.
- List visible_details that can be verified directly in this image.
- Select scene_suitability values from: hero, context, interaction, detail, side, rear, top, scale.
- List risk_flags such as screenshot, banner, collage, excessive_text, watermark, occlusion,
  misleading_angle, wrong_variant or unclear_identity. Eligible images must have no risk flags.

Eligibility Rule:
- Total score = identity_score + clarity_score + usability_score.
- An image is "eligible" ONLY IF total score >= 80, verdict is "pass", and hard_failure is false.

Respond ONLY with valid JSON in this exact structure:
{{
  "identity_score": <int 0-60>,
  "clarity_score": <int 0-25>,
  "usability_score": <int 0-15>,
  "total_score": <int 0-100>,
  "verdict": "<pass | fail | unknown>",
  "eligible": <true | false>,
  "hard_failure": <true | false>,
  "source_branding_detected": <true | false>,
  "identity_mismatch": <true | false>,
  "view_angle": "<front | front three-quarter | side | rear | top | close-up controls | other>",
  "shot_type": "<clean product | hero | context | interaction | detail>",
  "visible_details": ["<directly visible product detail>"],
  "scene_suitability": ["<hero | context | interaction | detail | side | rear | top | scale>"],
  "risk_flags": ["<risk flag, empty only for clean references>"],
  "text_coverage_percent": <int 0-100>,
  "reason": "<clear explanation of evaluation>"
}}"""


VIDEO_QC_SYSTEM_PROMPT = """You are a rigorous AI Quality Control inspector for marketing video generation.
You will be shown:
- Image 1: The approved product reference image.
- Subsequent Images: 5 sample frames extracted from a video scene (Start, 25%, 50%, 75%, End).
Evaluate visual fidelity, identity consistency, interaction contact geometry, product count, and cleanliness.
Reject wrong variant, changed silhouette, changed port/display/logo placement, duplicate products,
cable entering forbidden regions, morphing/melting, seller/shop/source branding, watermarks, marketplace UI,
captions, and heavy persistent letterboxing/pillarboxing as hard failures. Sub-1% video edge margins are normal and must not be flagged as black bars. Physical product branding is allowed only when it belongs
to the locked target product identity.
Only when the scene prompt says its provider provenance is verified Google Flow, allow Google Flow's native watermark (including its sparkle mark). Text watermarks from source images, seller marks, and all third-party watermarks remain hard failures. Set native_flow_watermark_only true only when that permitted mark is the sole visual issue.
Return strictly valid JSON."""


def build_video_sampling_qc_prompt(
    scene_number: int,
    scene_intent: str,
    brand: str,
    model: str,
    sample_timestamps: list[float],
    provider_kind: str = "",
) -> str:
    ts_str = ", ".join(f"{t:.2f}s" for t in sample_timestamps)
    flow_exception = (
        "Verified scene provider: Google Flow. Its native watermark, including the sparkle mark, is allowed. "
        "Reject source-image text, seller branding, and all third-party watermarks."
        if provider_kind == "google_flow" else
        "No provider watermark exception applies to this scene."
    )
    return f"""Target Product: {brand} {model}
Scene #{scene_number} Target Intent: "{scene_intent}"
Sample Timestamps: [{ts_str}]
{flow_exception}

The first image is the APPROVED PRODUCT REFERENCE.
The subsequent images are 5 sample frames from Scene #{scene_number} (Start, 25%, 50%, 75%, End).

Evaluate the sample frames according to this 100-point rubric:
1. Identity Consistency & Product Count (0 - 50 points):
   - Does the product in all 5 video frames match the design, color, shape, silhouette, and key features of the reference?
   - Is the product count correct (e.g. exactly one single speaker/charger, or exactly 1 pair of earbuds in 1 case)? Are there unwanted duplicated or extra products?
   - Are ports, buttons, displays, and logos positioned at their verified physical locations?
   - If the product completely morphed, changed into another object, shows wrong variant, or has duplicated units: hard_failure MUST be true.
2. Scene & Interaction Geometry Adherence (0 - 30 points):
   - Do the frames reflect the intended action, angle, start/end progression, and atmosphere?
   - If this scene involves physical interaction (e.g. plugging a cable, placing an earbud into cradle, pressing a button):
     does contact occur at the correct landmark? Did the actor/cable avoid forbidden regions (e.g. cable MUST NOT enter front screen/display)?
   - Any violation of contact landmark or cable entering forbidden region: hard_failure MUST be true.
3. Visual Cleanliness & Temporal Stability (0 - 20 points):
   - Are the frames free from seller/shop/source branding, disallowed watermarks, marketplace UI, captions/CTA text, and prominent persistent black bars (letterboxing/pillarboxing)? (Note: sub-1% pixel edge margins from video encoding are normal and not black bars).
   - Any source-store contamination, text overlay in video, wrong identity, or major letterboxing: hard_failure MUST be true.

Pass Rule:
- Total score = identity_consistency + scene_adherence + visual_cleanliness.
- Scene passes if total score >= 80, hard_failure is false, and verdict is "pass".

Respond ONLY with valid JSON in this exact structure:
{{
  "identity_consistency": <int 0-50>,
  "scene_adherence": <int 0-30>,
  "visual_cleanliness": <int 0-20>,
  "total_score": <int 0-100>,
  "verdict": "<pass | fail | unknown>",
  "hard_failure": <true | false>,
  "source_branding_detected": <true | false>,
  "native_flow_watermark_only": <true | false>,
  "identity_mismatch": <true | false>,
  "interaction_geometry_valid": <true | false>,
  "product_count_valid": <true | false>,
  "recommended_action": "<specific scene recovery action if failed, e.g. retry_scene with adjusted angle or simpler contact>",
  "reason": "<clear explanation of evaluation>"
}}"""


KEYFRAME_QC_SYSTEM_PROMPT = """You are a rigorous product-video keyframe QC inspector.
The first images are approved product references and the final image is the generated scene keyframe.
Judge product identity, adherence to the approved scene start state, and visual cleanliness.
Also judge whether the prompt agrees with the selected references, identity-critical details remain
visible, the composition is usable, and the start frame has physical room for the requested animation.
Seller/shop branding, source watermarks, marketplace UI, prices, ratings, unrelated logos,
wrong product identity, or malformed product geometry are hard failures. Return strictly valid JSON."""


def build_keyframe_qc_prompt(
    *,
    brand: str,
    model: str,
    scene_id: str,
    scene_prompt: str,
    candidate_dimensions: tuple[int, int] | None = None,
) -> str:
    dimensions = (
        f"Verified generated candidate dimensions: {candidate_dimensions[0]}x{candidate_dimensions[1]} pixels. "
        f"The candidate is {'portrait' if candidate_dimensions[1] > candidate_dimensions[0] else 'landscape' if candidate_dimensions[0] > candidate_dimensions[1] else 'square'}.\n"
        if candidate_dimensions else ""
    )
    return f"""Target product: {brand} {model}
Keyframe scene: {scene_id}
Approved scene prompt: {scene_prompt}
{dimensions}Evaluate only the final image as the generated candidate; earlier images are product references.

Evaluate this 100-point rubric:
1. identity_consistency (0-50): the generated product preserves the approved product shape,
   color, controls, proportions and distinguishing details.
2. scene_adherence (0-30): the image depicts the approved environment, start state and action setup.
3. visual_cleanliness (0-20): the image is coherent and contains no seller/source contamination,
   marketplace UI, watermarks, price/rating badges, malformed text or severe artifacts.

Boolean gates (all must be true to pass):
- prompt_reference_consistent: prompt, selected references and rendered product agree.
- important_details_preserved: identity-critical shape, color, material, controls and details remain.
- composition_usable: product is legible, uncropped where required and placed as requested.
- animation_suitable: start state leaves plausible room for the approved action and state change.

Pass only when total_score >= 80, verdict is pass and hard_failure is false.
Return only JSON:
{{
  "identity_consistency": <int 0-50>,
  "scene_adherence": <int 0-30>,
  "visual_cleanliness": <int 0-20>,
  "total_score": <int 0-100>,
  "verdict": "<pass | fail | unknown>",
  "hard_failure": <true | false>,
  "source_branding_detected": <true | false>,
  "identity_mismatch": <true | false>,
  "prompt_reference_consistent": <true | false>,
  "important_details_preserved": <true | false>,
  "composition_usable": <true | false>,
  "animation_suitable": <true | false>,
  "recommended_action": "<specific correction grounded in the failed check>",
  "reason": "<clear explanation>"
}}"""
