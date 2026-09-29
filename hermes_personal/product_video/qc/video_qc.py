"""Video Quality Control (Technical & Visual Sampling QC)."""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import av

from hermes_personal.integrations.video_factory.composer import check_black_bars_in_video
from hermes_personal.product_video.qc.evaluator import (
    QCResponseParseError,
    MultimodalEvaluator,
    validate_qc_response,
)
from hermes_personal.product_video.qc.fingerprint import (
    VIDEO_POLICY_VERSION,
    VIDEO_RUBRIC_VERSION,
    qc_fingerprint,
)
from hermes_personal.product_video.qc.models import (
    NormalizedProduct,
    QCReport,
    QCStage,
    QCVerdict,
)
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.qc.rubric import (
    VIDEO_QC_SYSTEM_PROMPT,
    build_video_sampling_qc_prompt,
)

logger = logging.getLogger(__name__)


def _black_bar_disagreement(evaluation: dict[str, Any], technical: dict[str, Any]) -> bool:
    """Keep a visual black-bar allegation from overruling contradictory bytes."""
    reason = str(evaluation.get("reason") or "").lower()
    alleges_bars = any(term in reason for term in ("black bars", "letterbox", "pillarbox", "viền đen", "dải đen", "thanh đen"))
    measured = technical.get("black_bars") or {}
    return bool(
        alleges_bars
        and (evaluation.get("hard_failure") or evaluation.get("verdict") == "fail")
        and measured.get("samples_checked", 0) > 0
        and measured.get("has_persistent_black_bars") is False
        and not evaluation.get("source_branding_detected", False)
        and not evaluation.get("identity_mismatch", False)
        and evaluation.get("interaction_geometry_valid", True)
        and evaluation.get("product_count_valid", True)
    )


def _allow_verified_flow_native_mark(
    evaluation: dict[str, Any], provider_kind: str
) -> dict[str, Any]:
    """Accept only the native Flow mark when Flow provenance is verified."""
    if (
        provider_kind != "google_flow"
        or evaluation.get("native_flow_watermark_only") is not True
        or evaluation.get("identity_mismatch") is True
        or evaluation.get("interaction_geometry_valid") is False
        or evaluation.get("product_count_valid") is False
        or int(evaluation.get("total_score") or 0) < 80
    ):
        return evaluation
    normalized = dict(evaluation)
    normalized["source_branding_detected"] = False
    normalized["hard_failure"] = False
    normalized["verdict"] = "pass"
    normalized["flow_native_mark_allowed"] = True
    return normalized


def compute_file_sha256(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_technical_video_specs(
    video_path: str | Path,
    expected_duration: float = 16.0,
    duration_tolerance: float = 0.5,
    check_black_bars: bool = True,
) -> dict[str, Any]:
    """Inspect technical specs, decode all frames, and check for black bars."""
    p = Path(video_path)
    if not p.is_file():
        return {
            "technical_pass": False,
            "error": f"File does not exist: {video_path}",
        }

    try:
        container = av.open(str(p))
    except Exception as exc:
        return {"technical_pass": False, "error": f"Cannot decode video container: {exc}"}
    video_streams = [s for s in container.streams if s.type == "video"]
    if not video_streams:
        container.close()
        return {
            "technical_pass": False,
            "error": "No video stream found in container",
        }

    v_stream = video_streams[0]
    audio_streams = [s for s in container.streams if s.type == "audio"]
    has_audio = len(audio_streams) > 0
    audio_codec = audio_streams[0].codec_context.name if has_audio else None

    # Decode all frames to ensure stream integrity
    decoded_frames = 0
    try:
        for _ in container.decode(v_stream):
            decoded_frames += 1
    except Exception as exc:
        container.close()
        return {
            "technical_pass": False,
            "error": f"Frame decoding error during technical QC: {exc}",
            "decoded_frames": decoded_frames,
        }

    # Duration check
    duration_sec = float(v_stream.duration * v_stream.time_base) if v_stream.duration else 0.0
    if duration_sec <= 0.0 and container.duration:
        duration_sec = float(container.duration / av.time_base)

    width = v_stream.codec_context.width
    height = v_stream.codec_context.height
    fps = float(v_stream.average_rate) if v_stream.average_rate else 24.0
    container.close()

    dur_ok = abs(duration_sec - expected_duration) <= duration_tolerance
    dim_ok = (width == 720 and height == 1280)
    frames_ok = decoded_frames > 0

    issues = []
    if not dur_ok:
        issues.append(f"Duration {duration_sec:.2f}s deviates from expected {expected_duration:.2f}s by >{duration_tolerance}s")
    if not dim_ok:
        issues.append(f"Dimensions {width}x{height} do not match required 720x1280")
    if not frames_ok:
        issues.append("Decoded zero frames")

    black_bars_res: dict[str, Any] = {}
    has_black_bars = False
    if check_black_bars and p.is_file():
        black_bars_res = check_black_bars_in_video(p, num_samples=5, max_edge_coverage_ratio=0.02)
        has_black_bars = bool(black_bars_res.get("has_persistent_black_bars", False))
        if has_black_bars:
            issues.append(
                f"Persistent black bars detected: top={black_bars_res.get('top_coverage', 0):.1%}, "
                f"bottom={black_bars_res.get('bottom_coverage', 0):.1%}, "
                f"left={black_bars_res.get('left_coverage', 0):.1%}, "
                f"right={black_bars_res.get('right_coverage', 0):.1%} (exceeds 2% limit)"
            )

    technical_pass = dur_ok and dim_ok and frames_ok and (not has_black_bars)

    return {
        "technical_pass": technical_pass,
        "width": width,
        "height": height,
        "duration_seconds": round(duration_sec, 2),
        "fps": round(fps, 2),
        "decoded_frames": decoded_frames,
        "has_audio": has_audio,
        "audio_codec": audio_codec,
        "black_bars": black_bars_res,
        "issues": issues,
    }


def extract_sample_frame_at_timestamp(video_path: str | Path, target_sec: float, out_path: str | Path) -> bool:
    container = av.open(str(video_path))
    v_stream = container.streams.video[0]
    tb = v_stream.time_base
    target_pts = int(target_sec / tb)

    # Seek close to target
    container.seek(target_pts, stream=v_stream, any_frame=False)
    best_frame = None
    min_diff = float("inf")

    for frame in container.decode(v_stream):
        curr_sec = float(frame.pts * tb) if frame.pts is not None else 0.0
        diff = abs(curr_sec - target_sec)
        if diff < min_diff:
            min_diff = diff
            best_frame = frame
        if curr_sec > target_sec + 0.5:
            break

    if best_frame is not None:
        img = best_frame.to_image()
        img.save(str(out_path), format="PNG")
        container.close()
        return True

    container.close()
    return False


def _resolve_scene_boundaries(
    storyboard: dict[str, Any],
    expected_duration: float,
    tolerance: float = 0.5,
) -> tuple[list[dict[str, Any]], str | None]:
    """Resolve explicit approved scene boundaries; never invent them for a PASS report."""
    raw_scenes = storyboard.get("scene_boundaries") or storyboard.get("scenes") or storyboard.get("frames")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        return [], "Approved storyboard has no scene boundaries"

    boundaries: list[dict[str, Any]] = []
    cursor = 0.0
    for idx, raw_scene in enumerate(raw_scenes, start=1):
        if not isinstance(raw_scene, dict):
            return [], f"Scene {idx} boundary is malformed"
        start_raw = raw_scene.get("start_seconds", raw_scene.get("start_time"))
        end_raw = raw_scene.get("end_seconds", raw_scene.get("end_time"))
        duration_raw = raw_scene.get("duration_seconds", raw_scene.get("duration"))
        try:
            start = float(start_raw) if start_raw is not None else cursor
            if end_raw is not None:
                end = float(end_raw)
            elif duration_raw is not None:
                end = start + float(duration_raw)
            else:
                return [], f"Scene {idx} is missing approved duration/boundary"
        except (TypeError, ValueError):
            return [], f"Scene {idx} boundary is not numeric"
        if start < 0 or end <= start:
            return [], f"Scene {idx} boundary is invalid ({start}, {end})"
        if boundaries and start < boundaries[-1]["end_seconds"] - 0.01:
            return [], f"Scene {idx} overlaps the previous approved scene"
        boundaries.append({
            "scene_number": idx,
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": end - start,
        })
        cursor = end

    if abs(boundaries[-1]["end_seconds"] - expected_duration) > tolerance:
        return [], (
            f"Approved scene boundaries end at {boundaries[-1]['end_seconds']:.2f}s, "
            f"expected {expected_duration:.2f}s"
        )
    return boundaries, None


def run_video_qc(
    workflow_id: str,
    video_path: str | Path,
    storyboard: dict[str, Any],
    product: NormalizedProduct,
    approved_reference_paths: list[str | Path],
    expected_duration: float = 16.0,
    evaluator: MultimodalEvaluator | None = None,
    repo: QCReportRepository | None = None,
    attempt_id: str = "",
    owner_user_id: str = "",
    project_id: str = "",
    artifact_id: str = "",
    artifact_version: int = 1,
    scene_provider_kinds: list[str] | None = None,
) -> QCReport:
    """Run comprehensive technical and visual sampling QC on final composite video."""
    video_path = Path(video_path)
    owner_user_id = str(owner_user_id or "").strip()
    project_id = str(project_id or "").strip()
    artifact_id = str(artifact_id or "").strip()
    if not owner_user_id or not project_id:
        raise ValueError("owner_user_id and project_id are required for Video QC")
    if not artifact_id:
        raise ValueError("artifact_id is required for Video QC")
    if (
        isinstance(artifact_version, bool)
        or not isinstance(artifact_version, int)
        or artifact_version < 1
    ):
        raise ValueError("artifact_version must be a positive integer for Video QC")
    artifact_digest = compute_file_sha256(video_path)

    if evaluator is None:
        evaluator = MultimodalEvaluator()
    provider_mode = "fake" if getattr(evaluator, "fake_mode", False) else "configured"
    evaluator_name = str(getattr(evaluator, "evaluator_name", "unknown"))
    evaluator_version = str(getattr(evaluator, "evaluator_version", "unknown"))
    model_identifier = str(getattr(evaluator, "model", ""))
    current_ref_digests = [compute_file_sha256(p) for p in approved_reference_paths if Path(p).is_file()]
    report_fingerprint = qc_fingerprint(
        workflow_id,
        QCStage.VIDEO,
        artifact_digest,
        product,
        evaluator_name=evaluator_name,
        evaluator_version=evaluator_version,
        model_identifier=model_identifier,
        storyboard=storyboard,
        video_sha256=artifact_digest,
        reference_digests=current_ref_digests,
        attempt_id=attempt_id,
        scene_provider_kinds=scene_provider_kinds,
    )

    # Check cached report
    if repo is not None:
        cached_report = repo.get_latest_report(
            workflow_id,
            QCStage.VIDEO,
            expected_artifact_digest=artifact_digest,
            expected_fingerprint=report_fingerprint,
            owner_user_id=owner_user_id,
            project_id=project_id,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
        )
        if cached_report is not None:
            logger.info("Reusing existing valid Video QC report %s for workflow %s", cached_report.report_id, workflow_id)
            return cached_report

    # 1. Technical QC
    tech_res = check_technical_video_specs(video_path, expected_duration=expected_duration)

    # 2. Visual Sampling QC
    frames_meta = storyboard.get("frames", [])
    scene_boundaries, coverage_error = _resolve_scene_boundaries(storyboard, expected_duration)
    scene_count = len(scene_boundaries)
    verified_scene_providers = (
        scene_provider_kinds
        if isinstance(scene_provider_kinds, list)
        and len(scene_provider_kinds) == scene_count
        and all(kind in {"google_flow", "vertex_ai"} for kind in scene_provider_kinds)
        else []
    )

    ref_path = approved_reference_paths[0] if approved_reference_paths else None
    ref_digests = current_ref_digests

    scene_results = []
    all_sample_timestamps = []
    visual_scores = []
    has_visual_hard_fail = False
    has_visual_unknown = False

    with tempfile.TemporaryDirectory() as tmp_dir:
        for idx, boundary in enumerate(scene_boundaries):
            sc_num = int(boundary["scene_number"])
            t_start = float(boundary["start_seconds"])
            scene_dur = float(boundary["duration_seconds"])
            # 5 sample points inside the scene: start (5%), 25%, 50%, 75%, end (95%)
            t_samples = [
                round(t_start + 0.05 * scene_dur, 2),
                round(t_start + 0.25 * scene_dur, 2),
                round(t_start + 0.50 * scene_dur, 2),
                round(t_start + 0.75 * scene_dur, 2),
                round(t_start + 0.95 * scene_dur, 2),
            ]
            sample_paths = []
            actual_sample_timestamps = []
            for s_idx, t_val in enumerate(t_samples):
                frame_png = Path(tmp_dir) / f"scene_{sc_num}_sample_{s_idx+1}.png"
                ok = extract_sample_frame_at_timestamp(video_path, t_val, frame_png)
                if ok:
                    sample_paths.append(frame_png)
                    actual_sample_timestamps.append(t_val)

            sc_intent = ""
            scene_meta = frames_meta[idx] if idx < len(frames_meta) and isinstance(frames_meta[idx], dict) else boundary
            sc_intent = (
                scene_meta.get("description")
                or scene_meta.get("prompt")
                or scene_meta.get("intent")
                or scene_meta.get("purpose")
                or scene_meta.get("objective")
                or scene_meta.get("main_action")
                or ""
            )

            if not sc_intent or len(sample_paths) != 5:
                has_visual_hard_fail = True
                scene_results.append({
                    "scene_number": sc_num,
                    "intent": sc_intent,
                    "sample_timestamps": actual_sample_timestamps,
                    "samples_extracted": len(sample_paths),
                    "score": 0,
                    "verdict": "unknown",
                    "hard_failure": False,
                    "recovery_action": f"retry_scene_{sc_num}",
                    "error": "Scene intent or one of the five required samples is missing",
                })
                continue

            all_sample_timestamps.extend(actual_sample_timestamps)

            prompt = build_video_sampling_qc_prompt(
                scene_number=sc_num,
                scene_intent=sc_intent,
                brand=product.brand,
                model=product.model,
                sample_timestamps=t_samples,
                provider_kind=verified_scene_providers[idx] if verified_scene_providers else "",
            )

            if ref_path and sample_paths and Path(ref_path).is_file():
                eval_images = [ref_path] + sample_paths
                try:
                    raw_evaluation = evaluator.evaluate_multiple_images(
                        image_paths=eval_images,
                        prompt=prompt,
                        system_instruction=VIDEO_QC_SYSTEM_PROMPT,
                    )
                    eval_res = validate_qc_response(
                        _allow_verified_flow_native_mark(
                            raw_evaluation,
                            verified_scene_providers[idx] if verified_scene_providers else "",
                        ),
                        QCStage.VIDEO,
                    )
                    sc_score = int(eval_res.get("total_score", 0))
                    sc_hard_fail = bool(
                        eval_res.get("hard_failure", False)
                        or eval_res.get("source_branding_detected", False)
                        or eval_res.get("identity_mismatch", False)
                        or (not eval_res.get("interaction_geometry_valid", True))
                        or (not eval_res.get("product_count_valid", True))
                    )
                    sc_verdict = str(eval_res.get("verdict", "fail")).lower()
                    visual_scores.append(sc_score)
                    disagreement = _black_bar_disagreement(eval_res, tech_res)
                    if disagreement:
                        has_visual_unknown = True
                        sc_verdict = "unknown"
                    elif sc_hard_fail or sc_verdict != "pass" or sc_score < 80:
                        has_visual_hard_fail = True
                    rec_action = str(eval_res.get("recommended_action") or "").strip()
                    if disagreement:
                        rec_action = "manual_review_technical_conflict"
                    elif not rec_action and (sc_hard_fail or sc_verdict != "pass" or sc_score < 80):
                        rec_action = f"retry_scene_{sc_num}"
                    scene_results.append({
                        "scene_number": sc_num,
                        "provider_kind": verified_scene_providers[idx] if verified_scene_providers else "",
                        "intent": sc_intent,
                        "sample_timestamps": actual_sample_timestamps,
                        "samples_extracted": len(sample_paths),
                        "score": sc_score,
                        "verdict": sc_verdict,
                        "hard_failure": sc_hard_fail,
                        "recovery_action": rec_action,
                        "arbitration": {
                            "status": "technical_conflict",
                            "measured_property": "persistent_black_bars",
                            "technical_samples": tech_res.get("black_bars", {}),
                        } if disagreement else None,
                        "findings": eval_res,
                    })
                except Exception as exc:
                    logger.error("Visual QC failed on scene %d: %s", sc_num, exc)
                    has_visual_hard_fail = True
                    diagnostics: dict[str, Any] = {}
                    if isinstance(exc, QCResponseParseError):
                        diagnostics = {
                            "raw_response": exc.raw_response,
                            "finish_reason": exc.finish_reason,
                            "parse_error": exc.parse_error,
                        }
                    scene_results.append({
                        "scene_number": sc_num,
                        "intent": sc_intent,
                        "sample_timestamps": actual_sample_timestamps,
                        "samples_extracted": len(sample_paths),
                        "score": 0,
                        "verdict": "fail",
                        "hard_failure": True,
                        "recovery_action": f"retry_scene_{sc_num}",
                        "error": str(exc),
                        "diagnostics": diagnostics,
                    })
            else:
                has_visual_hard_fail = True
                scene_results.append({
                    "scene_number": sc_num,
                    "intent": sc_intent,
                    "sample_timestamps": actual_sample_timestamps,
                    "samples_extracted": len(sample_paths),
                    "score": 0,
                    "verdict": "fail",
                    "hard_failure": True,
                    "recovery_action": f"retry_scene_{sc_num}",
                    "error": "Missing reference or failed sample extraction",
                })

    avg_visual_score = round(sum(visual_scores) / len(visual_scores)) if visual_scores else 0
    technical_pass = bool(tech_res.get("technical_pass", False))
    overall_pass = (
        technical_pass
        and coverage_error is None
        and scene_count > 0
        and (not has_visual_hard_fail)
        and (not has_visual_unknown)
        and (avg_visual_score >= 80)
    )
    verdict = QCVerdict.PASS if overall_pass else (
        QCVerdict.UNKNOWN
        if (coverage_error or has_visual_unknown) and technical_pass and not has_visual_hard_fail
        else QCVerdict.FAIL
    )

    report_id = f"qc_vid_{workflow_id}_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(timezone.utc).isoformat()
    findings = {
        "technical_specs": tech_res,
        "visual_scenes": scene_results,
        "recovery_actions": [
            r["recovery_action"]
            for r in scene_results
            if r.get("recovery_action") and (r.get("hard_failure") or r.get("verdict") != "pass" or r.get("score", 0) < 80)
        ],
        "sample_coverage": {
            "total_scenes_evaluated": scene_count,
            "samples_per_scene": 5,
            "total_samples": len(all_sample_timestamps),
            "expected_samples": scene_count * 5,
            "timestamps": all_sample_timestamps,
            "coverage_valid": coverage_error is None and scene_count > 0 and len(all_sample_timestamps) == scene_count * 5,
            "coverage_error": coverage_error,
            "boundaries": scene_boundaries,
        },
        "limitation_notice": (
            "Visual sampling evaluated 5 timestamps per scene against approved reference assets. "
            "This verifies continuity, absence of morphing, correct product count, and key scene fidelity, "
            "but does NOT guarantee every single intermediate frame is artifact-free. Final operator review is required."
        ),
        "attempt_id": attempt_id,
    }

    report = QCReport(
        report_id=report_id,
        workflow_id=workflow_id,
        stage=QCStage.VIDEO,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        artifact_digest=artifact_digest,
        reference_digests=ref_digests,
        evaluator_name=evaluator_name,
        evaluator_version=evaluator_version,
        rubric_version=VIDEO_RUBRIC_VERSION,
        created_at=created_at,
        score=avg_visual_score if technical_pass else 0,
        verdict=verdict,
        findings=findings,
        sample_timestamps=all_sample_timestamps,
        fingerprint=report_fingerprint,
        provider_mode=provider_mode,
        model_identifier=model_identifier,
        policy_version=VIDEO_POLICY_VERSION,
        owner_user_id=owner_user_id,
        project_id=project_id,
    )

    if repo is not None:
        repo.save_report(report)

    return report
