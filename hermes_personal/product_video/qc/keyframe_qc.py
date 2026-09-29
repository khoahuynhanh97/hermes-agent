"""QC for generated storyboard keyframes before human Gate 4."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evaluator import QCResponseParseError, MultimodalEvaluator, validate_qc_response
from .fingerprint import KEYFRAME_POLICY_VERSION, KEYFRAME_RUBRIC_VERSION, qc_fingerprint
from .models import NormalizedProduct, QCReport, QCStage, QCVerdict
from .repository import QCReportRepository
from .rubric import KEYFRAME_QC_SYSTEM_PROMPT, build_keyframe_qc_prompt
from hermes_personal.product_video.creative.storyboard import storyboard_package_digest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_digest(package: dict[str, Any]) -> str:
    supplied = str(package.get("package_digest") or "")
    if package.get("schema_version") == "storyboard-package-v2":
        computed = storyboard_package_digest(package)
        if supplied and supplied != computed:
            raise ValueError("storyboard package digest mismatch")
        return computed
    if supplied:
        return supplied
    encoded = json.dumps(package, sort_keys=True, ensure_ascii=False, default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def run_keyframe_qc(
    *,
    workflow_id: str,
    package: dict[str, Any],
    product: NormalizedProduct,
    evaluator: MultimodalEvaluator | Any | None = None,
    repo: QCReportRepository | None = None,
    attempt_id: str = "",
    owner_user_id: str = "",
    project_id: str = "",
) -> QCReport:
    owner_user_id = str(owner_user_id or package.get("owner_user_id") or "").strip()
    project_id = str(project_id or package.get("project_id") or "").strip()
    if not owner_user_id or not project_id:
        raise ValueError("owner_user_id and project_id are required for Keyframe QC")
    artifact_id = str(package.get("storyboard_id") or "").strip()
    if not artifact_id:
        raise ValueError("storyboard_id is required for Keyframe QC")
    artifact_version = package.get("version")
    if (
        isinstance(artifact_version, bool)
        or not isinstance(artifact_version, int)
        or artifact_version < 1
    ):
        raise ValueError("storyboard version must be a positive integer for Keyframe QC")

    frames = package.get("generated_keyframes")
    if not isinstance(frames, list) or not frames:
        raise ValueError("generated keyframe package is empty")
    evaluator = evaluator or MultimodalEvaluator()
    provider_mode = "fake" if getattr(evaluator, "fake_mode", False) else "configured"
    evaluator_name = str(getattr(evaluator, "evaluator_name", "unknown"))
    evaluator_version = str(getattr(evaluator, "evaluator_version", "unknown"))
    model_identifier = str(getattr(evaluator, "model", ""))
    artifact_digest = _artifact_digest(package)
    reference_digests: list[str] = []
    items: list[dict[str, Any]] = []

    for frame in frames:
        frame_id = str(frame.get("frame_id") or "")
        image_path = Path(str(frame.get("image_path") or "")).resolve()
        expected_sha = str(frame.get("sha256") or "").removeprefix("sha256:")
        references = [Path(str(value)).resolve() for value in frame.get("reference_image_paths", [])]
        if (
            not frame_id
            or not image_path.is_file()
            or image_path.stat().st_size == 0
            or _sha256(image_path) != expected_sha
            or not references
            or any(not path.is_file() or path.stat().st_size == 0 for path in references)
        ):
            items.append(
                {
                    "frame_id": frame_id,
                    "score": 0,
                    "verdict": "fail",
                    "hard_failure": True,
                    "reason": "keyframe or approved references are missing or changed",
                }
            )
            continue
        frame_reference_digests = [_sha256(path) for path in references]
        reference_digests.extend(frame_reference_digests)
        try:
            from PIL import Image

            try:
                with Image.open(image_path) as candidate:
                    candidate_dimensions = candidate.size
            except OSError:
                candidate_dimensions = None
            response = evaluator.evaluate_multiple_images(
                [*references, image_path],
                prompt=build_keyframe_qc_prompt(
                    brand=product.brand,
                    model=product.model,
                    scene_id=str(frame.get("scene_id") or frame_id),
                    scene_prompt=str(frame.get("prompt") or ""),
                    candidate_dimensions=candidate_dimensions,
                ),
                system_instruction=KEYFRAME_QC_SYSTEM_PROMPT,
            )
            normalized = validate_qc_response(response, QCStage.KEYFRAME)
            score = int(normalized["total_score"])
            hard_failure = bool(normalized["hard_failure"])
            verdict = str(normalized["verdict"])
            if score < 80 or hard_failure or verdict != "pass":
                verdict = "fail" if verdict != "unknown" else "unknown"
            items.append(
                {
                    "frame_id": frame_id,
                    "scene_id": frame.get("scene_id"),
                    "image_path": str(image_path),
                    "sha256": expected_sha,
                    "reference_digests": frame_reference_digests,
                    "score": score,
                    "verdict": verdict,
                    "hard_failure": hard_failure,
                    "reason": str(normalized.get("reason") or ""),
                    "prompt_reference_consistent": bool(
                        normalized.get("prompt_reference_consistent", True)
                    ),
                    "important_details_preserved": bool(
                        normalized.get("important_details_preserved", True)
                    ),
                    "composition_usable": bool(normalized.get("composition_usable", True)),
                    "animation_suitable": bool(normalized.get("animation_suitable", True)),
                    "recommended_action": str(normalized.get("recommended_action") or ""),
                    "findings": normalized,
                }
            )
        except Exception as exc:
            diagnostics: dict[str, Any] = {}
            if isinstance(exc, QCResponseParseError):
                diagnostics = {
                    "raw_response": exc.raw_response,
                    "finish_reason": exc.finish_reason,
                    "parse_error": exc.parse_error,
                }
            items.append(
                {
                    "frame_id": frame_id,
                    "score": 0,
                    "verdict": "unknown",
                    "hard_failure": False,
                    "reason": f"Evaluation call failed: {exc}",
                    "findings": diagnostics,
                }
            )

    if any(item["verdict"] == "unknown" for item in items):
        verdict = QCVerdict.UNKNOWN
    elif all(item["verdict"] == "pass" and not item["hard_failure"] for item in items):
        verdict = QCVerdict.PASS
    else:
        verdict = QCVerdict.FAIL
    score = round(sum(int(item["score"]) for item in items) / len(items))
    fingerprint = qc_fingerprint(
        workflow_id,
        QCStage.KEYFRAME,
        artifact_digest,
        product,
        evaluator_name=evaluator_name,
        evaluator_version=evaluator_version,
        model_identifier=model_identifier,
        storyboard=package,
        reference_digests=reference_digests,
        attempt_id=attempt_id,
    )
    recovery_frames: list[dict[str, Any]] = []
    for item in items:
        if item.get("verdict") == "pass" and not item.get("hard_failure"):
            continue
        actions: list[str] = []
        if (
            bool(item.get("hard_failure"))
            or not bool(item.get("important_details_preserved", True))
            or bool(item.get("findings", {}).get("identity_mismatch"))
        ):
            actions.append("reselect_reference")
        if not bool(item.get("prompt_reference_consistent", True)):
            actions.append("rewrite_prompt")
        if not bool(item.get("composition_usable", True)) or not bool(
            item.get("animation_suitable", True)
        ):
            actions.append("adjust_composition")
        if not actions:
            actions.append("rewrite_prompt")
        actions.extend(("regenerate_keyframe", "rerun_keyframe_qc"))
        recovery_frames.append(
            {
                "frame_id": item.get("frame_id"),
                "scene_id": item.get("scene_id"),
                "actions": actions,
                "feedback": str(
                    item.get("recommended_action") or item.get("reason") or "Keyframe QC failed"
                ),
            }
        )

    report = QCReport(
        report_id=f"qc_keyframe_{workflow_id}_{uuid.uuid4().hex[:8]}",
        workflow_id=workflow_id,
        stage=QCStage.KEYFRAME,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        artifact_digest=artifact_digest,
        reference_digests=reference_digests,
        evaluator_name=evaluator_name,
        evaluator_version=evaluator_version,
        rubric_version=KEYFRAME_RUBRIC_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(),
        score=score,
        verdict=verdict,
        findings={
            "items": items,
            "passed_count": sum(item["verdict"] == "pass" for item in items),
            "total_count": len(items),
            "attempt_id": attempt_id,
            "recovery_plan": {
                "blocked_from_video": bool(recovery_frames),
                "frames": recovery_frames,
                "policy": "reselect/rewrite/adjust/regenerate/qc",
            },
        },
        fingerprint=fingerprint,
        provider_mode=provider_mode,
        model_identifier=model_identifier,
        policy_version=KEYFRAME_POLICY_VERSION,
        owner_user_id=owner_user_id,
        project_id=project_id,
    )
    if repo is not None:
        repo.save_report(report)
    return report
