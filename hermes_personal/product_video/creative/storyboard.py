"""Deterministic compilation of approved scenes into grounded keyframe requests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from hermes_personal.integrations.video_factory.ports import KeyframeGenerationRequest

from .contracts import ResearchDossier, ScriptScenePlanV2


KEYFRAME_NEGATIVE_PROMPT = (
    "seller or shop branding, source watermark, marketplace UI, price badge, rating badge, "
    "social handle, shipping label, unrelated logo, copied product-listing layout, malformed text, "
    "wrong brand, wrong model, wrong variant, changed color, changed material, changed logo, "
    "changed product shape, distorted geometry, duplicate product, duplicated product, extra product, "
    "floating object, missing control, missing identity detail, cropped identity detail, extra limbs, "
    "cable entering screen, cable entering forbidden region, wrong port placement, wrong display shape, "
    "wrong control placement, black bars, letterboxing, square composition"
)


def storyboard_package_digest(package: dict[str, object]) -> str:
    """Bind QC approval to every creative and generated-keyframe input."""

    payload = {
        "schema_version": package.get("schema_version"),
        "workflow_id": package.get("workflow_id"),
        "project_id": package.get("project_id"),
        "script": package.get("script"),
        "scenes": package.get("scenes"),
        "storyboard_frames": package.get("storyboard_frames"),
        "generated_keyframes": package.get("generated_keyframes"),
        "recovery_attempt": package.get("recovery_attempt", 0),
        "end_keyframe_omissions": package.get("end_keyframe_omissions", []),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_score(asset: object, scene: object) -> tuple[int, int, int, str]:
    scene_text = " ".join(
        str(value)
        for value in (
            getattr(scene, "story_role", ""),
            getattr(scene, "visual_objective", ""),
            getattr(scene, "subject_action", ""),
            getattr(scene, "product_interaction", ""),
            getattr(scene, "interaction_target", ""),
            getattr(scene, "contact_landmark", ""),
            *getattr(scene, "reference_requirements", ()),
        )
    ).casefold()
    tags = (
        getattr(asset, "view_angle", ""),
        getattr(asset, "shot_type", ""),
        *getattr(asset, "scene_suitability", ()),
        *getattr(asset, "visible_details", ()),
    )
    semantic_matches = sum(
        1 for tag in tags if str(tag).strip() and str(tag).casefold() in scene_text
    )
    rank = int(getattr(asset, "reference_rank", 0) or 10_000)
    return (
        semantic_matches,
        int(getattr(asset, "qc_score", 0) or 0),
        -rank,
        str(getattr(asset, "asset_id", "")),
    )


def _select_scene_assets(assets: dict[str, object], scene: object) -> list[object]:
    requested = [
        assets[asset_id]
        for asset_id in getattr(scene, "reference_asset_ids", ())
        if asset_id in assets
    ]
    candidates = requested or list(assets.values())
    candidates.sort(key=lambda asset: _reference_score(asset, scene), reverse=True)
    return candidates[: min(2, len(candidates))]


def compile_keyframe_requests(
    *,
    workflow_id: str,
    project_id: str,
    dossier: ResearchDossier,
    script: ScriptScenePlanV2,
    recovery_plan: dict[str, Any] | None = None,
    recovery_attempt: int = 0,
    previous_package: dict[str, Any] | None = None,
) -> tuple[KeyframeGenerationRequest, ...]:
    assets = {asset.asset_id: asset for asset in dossier.eligible_assets}
    product = dossier.product_identity
    description = " ".join(
        value
        for value in (
            product.brand,
            product.model,
            product.variant,
            product.shape,
            product.color,
            product.materials,
            product.logo_placement,
            product.silhouette,
            product.main_proportions,
            product.product_count,
            product.control_placement,
            product.port_count,
            product.port_placement,
            product.display_shape,
            *product.distinctive_features,
        )
        if value
    )
    requests = []
    recovery_by_frame = {
        str(item.get("frame_id")): item
        for item in (recovery_plan or {}).get("frames", [])
        if isinstance(item, dict) and item.get("frame_id")
    }
    previous_by_frame = {
        str(item.get("frame_id")): item
        for item in (previous_package or {}).get("generated_keyframes", [])
        if isinstance(item, dict) and item.get("frame_id")
    }
    for scene in script.scenes:
        frame_id = f"{scene.scene_id}-start"
        recovery = recovery_by_frame.get(frame_id)
        recovery_actions = tuple(str(value) for value in (recovery or {}).get("actions", []))
        recovery_feedback = str((recovery or {}).get("feedback") or "").strip()
        references = []
        unknown_ids = set(scene.reference_asset_ids) - set(assets)
        if unknown_ids:
            raise ValueError(f"scene references a non-eligible asset: {sorted(unknown_ids)[0]}")
        selected_assets = _select_scene_assets(assets, scene)
        if recovery and "reselect_reference" in recovery_actions:
            previous_paths = {
                str(Path(str(value)).resolve())
                for value in previous_by_frame.get(frame_id, {}).get(
                    "reference_image_paths", []
                )
            }
            all_candidates = sorted(
                assets.values(),
                key=lambda asset: _reference_score(asset, scene),
                reverse=True,
            )
            unseen = [
                asset
                for asset in all_candidates
                if str(Path(str(getattr(asset, "path", ""))).resolve()) not in previous_paths
            ]
            selected_assets = (unseen + [asset for asset in all_candidates if asset not in unseen])[
                : min(2, len(all_candidates))
            ]
        for asset in selected_assets:
            asset_id = asset.asset_id
            path = Path(asset.path).resolve()
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"eligible reference is missing: {asset_id}")
            if _file_sha256(path) != asset.sha256.removeprefix("sha256:"):
                raise ValueError(f"eligible reference digest changed: {asset_id}")
            references.append(str(path))
        if not references:
            raise ValueError(f"scene has no eligible product reference: {scene.scene_id}")
        operation_payload = (
            f"{workflow_id}|{project_id}|{script.digest()}|{scene.scene_id}|start-keyframe-v2"
        )
        if recovery:
            operation_payload += (
                f"|recovery:{recovery_attempt}|{','.join(recovery_actions)}|{recovery_feedback}"
            )
        operation_id = "keyframe-" + hashlib.sha256(operation_payload.encode()).hexdigest()[:24]
        reference_profiles = "; ".join(
            f"[{index}] {asset.asset_id}: angle={asset.view_angle or 'unspecified'}, "
            f"shot={asset.shot_type or 'unspecified'}, visible={', '.join(asset.visible_details) or 'unspecified'}"
            for index, asset in enumerate(selected_assets, start=1)
        )
        identity_cues = ", ".join(
            scene.product_identity_cues
            or tuple(
                value
                for value in (
                    product.shape,
                    product.color,
                    product.materials,
                    product.logo_placement,
                    product.silhouette,
                    product.product_count,
                    product.control_placement,
                    product.port_placement,
                    product.display_shape,
                    *product.distinctive_features,
                )
                if value
            )
        )
        required_details = ", ".join(scene.required_visible_details)
        interaction_cues = []
        if scene.contact_landmark:
            interaction_cues.append(f"Contact landmark: {scene.contact_landmark}")
        if scene.approach_vector:
            interaction_cues.append(f"Approach vector: {scene.approach_vector}")
        if scene.object_orientation:
            interaction_cues.append(f"Orientation: {scene.object_orientation}")
        if scene.forbidden_contact_regions:
            interaction_cues.append(f"Forbidden contact regions: {', '.join(scene.forbidden_contact_regions)}")
        interaction_text = f"\nInteraction geometry: {'; '.join(interaction_cues)}." if interaction_cues else ""

        product_outside_start = any(
            phrase in scene.start_state.casefold()
            for phrase in ("out of frame", "outside the frame", "not visible")
        )
        start_subject = (
            f"the environment immediately before the exact product {product.display_name} ({description}) enters the shot"
            if product_outside_start
            else f"the exact product {product.display_name} ({description})"
        )
        start_presence = (
            "This START image shows the empty tabletop before the action. No speaker, hand, glass, "
            "or other object is visible on or above the table. The product reference is supplied "
            "only to identify the object that will enter in the later video; do not reproduce it in this image. "
            "The product and the hand holding it must remain outside the image at this START moment."
            if product_outside_start
            else "Show exactly one product unit; do not add a duplicate, replacement model, wrong variant or unrelated product."
        )
        prompt = f"""Create a photorealistic vertical commercial keyframe of {start_subject}.
This is the START frame for scene {scene.order} ({scene.story_role}).
Approved reference profiles: {reference_profiles}.
Immutable identity cues: {identity_cues or 'match the approved references exactly'}.
Environment: {scene.environment}.
Visual objective: {scene.visual_objective}.
Subject action that is about to happen: {scene.subject_action}.
Product interaction: {scene.product_interaction}.{interaction_text}
Exact visible start state: {scene.start_state}.
The later end state will be: {scene.end_state}.
Frame as: {scene.camera_framing}. Camera intent: {scene.camera_movement}.
Product placement: {('outside the frame at this start moment' if product_outside_start else scene.product_placement or 'keep the complete product clearly visible and unobstructed')}.
Lighting: {scene.lighting or 'natural commercial lighting that preserves true product color and material'}.
Continuity into this scene: {scene.continuity_from_previous or 'preserve the approved product unit'}.
Continuity out of this scene: {scene.continuity_to_next or 'keep product identity and orientation stable'}.
Required visible details: {('the environment and the empty placement area; product details appear only after entry' if product_outside_start else required_details or identity_cues or 'all identity-critical product details')}.
Preserve exact proportions, variant, color, material, controls, logo placement and distinctive details from the references.
Create a believable real-use situation with people/hands only when required by the action.
Render one continuous photographic moment in a single portrait frame; never create a collage, panels, split screen, or a sequence of views.
Do not place promotional copy, captions, prices, badges or UI inside the image.
{start_presence}
This image is a visual storyboard reference for the later scene video, not a final frame with text."""
        if recovery:
            prompt += (
                f"\nRecovery attempt {recovery_attempt}. QC feedback: {recovery_feedback or 'correct the failed fidelity checks'}."
                f" Required recovery actions: {', '.join(recovery_actions) or 'regenerate_keyframe'}."
                " Correct these issues while preserving every approved fact and identity constraint above."
            )
        requests.append(
            KeyframeGenerationRequest(
                operation_id=operation_id,
                workflow_id=workflow_id,
                project_id=project_id,
                frame_id=frame_id,
                prompt=prompt,
                product_description=description,
                reference_image_paths=tuple(references),
                aspect_ratio="9:16",
                negative_prompt=KEYFRAME_NEGATIVE_PROMPT,
                frame_role="start",
            )
        )

        # Explicitly model end keyframe or structured safety omission
        # If end keyframe is requested or planned, generate end keyframe request; otherwise record safety reason
        end_frame_id = f"{scene.scene_id}-end"
        end_recovery = recovery_by_frame.get(end_frame_id)
        end_requested = (
            scene.end_keyframe_policy in ("generated", "required")
            or (recovery and "generate_end_keyframe" in recovery_actions)
            or end_recovery is not None
        )
        if end_requested:
            end_op_payload = f"{workflow_id}|{project_id}|{script.digest()}|{scene.scene_id}|end-keyframe-v2"
            if end_recovery or (recovery and "generate_end_keyframe" in recovery_actions):
                end_op_payload += f"|recovery:{recovery_attempt}"
            end_op_id = "keyframe-" + hashlib.sha256(end_op_payload.encode()).hexdigest()[:24]
            end_prompt = f"""Create a photorealistic vertical commercial keyframe of the exact product {product.display_name} ({description}).
This is the END frame for scene {scene.order} ({scene.story_role}).
Approved reference profiles: {reference_profiles}.
Immutable identity cues: {identity_cues or 'match the approved references exactly'}.
Environment: {scene.environment}.
Exact visible end state: {scene.end_state}.
Visual change completed: {scene.visual_change}.
Frame as: {scene.camera_framing}.
Lighting: {scene.lighting or 'natural commercial lighting'}.
Required visible details: {required_details or identity_cues or 'all identity-critical product details'}.
Preserve exact proportions, variant, color, material, controls, and logo placement."""
            if end_recovery:
                end_prompt += (
                    f"\nRecovery attempt {recovery_attempt}. QC feedback: "
                    f"{end_recovery.get('feedback') or 'correct the failed scene continuity'}. "
                    "Keep the exact approved START-frame setting while correcting this END frame."
                )
            requests.append(
                KeyframeGenerationRequest(
                    operation_id=end_op_id,
                    workflow_id=workflow_id,
                    project_id=project_id,
                    frame_id=end_frame_id,
                    prompt=end_prompt,
                    product_description=description,
                    reference_image_paths=tuple(references),
                    aspect_ratio="9:16",
                    negative_prompt=KEYFRAME_NEGATIVE_PROMPT,
                    frame_role="end",
                )
            )
    return tuple(requests)
