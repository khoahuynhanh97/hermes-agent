"""Image Quality Control (Vision QC) for Product Video Resource Pack."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_personal.product_video.qc.evaluator import (
    QCResponseParseError,
    MultimodalEvaluator,
    validate_qc_response,
)
from hermes_personal.product_video.qc.fingerprint import (
    IMAGE_POLICY_VERSION,
    IMAGE_RUBRIC_VERSION,
    qc_fingerprint,
)
from hermes_personal.product_video.qc.models import (
    ImageQCItem,
    NormalizedProduct,
    QCReport,
    QCStage,
    QCVerdict,
)
from hermes_personal.product_video.qc.normalization import (
    _is_decodable_image,
    _media_manifest,
    _unwrap_resource_pack,
    resource_pack_fingerprint,
)
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.qc.rubric import (
    IMAGE_QC_SYSTEM_PROMPT,
    build_image_qc_prompt,
)

logger = logging.getLogger(__name__)


def compute_file_sha256(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_artifact_digest(artifact: dict[str, Any]) -> str:
    """Compute the canonical envelope-independent resource-pack fingerprint."""
    return resource_pack_fingerprint(artifact)


def run_image_qc(
    workflow_id: str,
    resource_pack: dict[str, Any],
    product: NormalizedProduct,
    evaluator: MultimodalEvaluator | None = None,
    repo: QCReportRepository | None = None,
    attempt_id: str = "",
    owner_user_id: str = "",
    project_id: str = "",
) -> tuple[QCReport, list[ImageQCItem]]:
    """Run multimodal vision QC on all candidate images in the resource pack."""
    raw_rp = _unwrap_resource_pack(resource_pack)
    owner_user_id = str(owner_user_id or raw_rp.get("owner_user_id") or "").strip()
    project_id = str(project_id or raw_rp.get("project_id") or "").strip()
    if not owner_user_id or not project_id:
        raise ValueError("owner_user_id and project_id are required for Image QC")

    artifact_id = str(raw_rp.get("resource_pack_id") or raw_rp.get("id") or "").strip()
    if not artifact_id:
        raise ValueError("resource_pack_id is required for Image QC")
    artifact_version = raw_rp.get("version")
    if (
        isinstance(artifact_version, bool)
        or not isinstance(artifact_version, int)
        or artifact_version < 1
    ):
        raise ValueError("resource pack version must be a positive integer for Image QC")
    artifact_digest = compute_artifact_digest(raw_rp)

    if evaluator is None:
        evaluator = MultimodalEvaluator()
    provider_mode = "fake" if getattr(evaluator, "fake_mode", False) else "configured"
    evaluator_name = str(getattr(evaluator, "evaluator_name", "unknown"))
    evaluator_version = str(getattr(evaluator, "evaluator_version", "unknown"))
    model_identifier = str(getattr(evaluator, "model", ""))
    report_fingerprint = qc_fingerprint(
        workflow_id,
        QCStage.IMAGE,
        artifact_digest,
        product,
        evaluator_name=evaluator_name,
        evaluator_version=evaluator_version,
        model_identifier=model_identifier,
        attempt_id=attempt_id,
    )

    # 1. Check if an up-to-date valid QC report already exists for this exact artifact digest
    if repo is not None:
        cached_report = repo.get_latest_report(
            workflow_id,
            QCStage.IMAGE,
            expected_artifact_digest=artifact_digest,
            expected_fingerprint=report_fingerprint,
            owner_user_id=owner_user_id,
            project_id=project_id,
        )
        if cached_report is not None:
            items: list[ImageQCItem] = []
            for d in cached_report.findings.get("items", []):
                items.append(
                    ImageQCItem(
                        asset_id=d["asset_id"],
                        uri=d["uri"],
                        digest=d["digest"],
                        score=d["score"],
                        identity_score=d["identity_score"],
                        clarity_score=d["clarity_score"],
                        usability_score=d["usability_score"],
                        verdict=QCVerdict(d["verdict"]),
                        eligible=d["eligible"],
                        hard_failure=d["hard_failure"],
                        reason=d["reason"],
                    )
                )
            eligible_order = {
                str(item.get("asset_id")): index
                for index, item in enumerate(
                    cached_report.findings.get("eligible_reference_manifest", [])
                )
                if isinstance(item, dict)
            }
            eligible_items = [item for item in items if item.eligible]
            eligible_items.sort(key=lambda item: eligible_order.get(item.asset_id, 10_000))
            return cached_report, eligible_items

    # 2. Extract asset list
    assets = _media_manifest(raw_rp)

    items: list[ImageQCItem] = []
    ref_digests: list[str] = []
    seen_digests: dict[str, str] = {}

    prompt = build_image_qc_prompt(
        brand=product.brand,
        model=product.model,
        variant=product.variant,
        display_name=product.display_name,
        key_features=product.verified_claims,
    )

    for i, asset in enumerate(assets):
        asset_id = str(asset.get("asset_id") or f"asset_{i+1}")
        local_path = asset.get("local_path") or asset.get("path") or asset.get("absolute_path")
        uri = asset.get("uri") or f"file:///{str(local_path).replace(chr(92), '/')}"

        if not local_path or not Path(local_path).is_file():
            items.append(
                ImageQCItem(
                    asset_id=asset_id,
                    uri=uri,
                    digest="",
                    score=0,
                    identity_score=0,
                    clarity_score=0,
                    usability_score=0,
                    verdict=QCVerdict.FAIL,
                    eligible=False,
                    hard_failure=True,
                    reason=f"Image file missing on disk: {local_path}",
                )
            )
            continue

        digest = compute_file_sha256(local_path)
        ref_digests.append(digest)

        duplicate_of = seen_digests.get(digest)
        if duplicate_of is not None:
            items.append(
                ImageQCItem(
                    asset_id=asset_id,
                    uri=uri,
                    digest=digest,
                    score=0,
                    identity_score=0,
                    clarity_score=0,
                    usability_score=0,
                    verdict=QCVerdict.FAIL,
                    eligible=False,
                    hard_failure=False,
                    reason=f"Exact duplicate of {duplicate_of}; excluded from reference diversity",
                    findings={"duplicate_of": duplicate_of, "risk_flags": ["duplicate"]},
                )
            )
            continue
        seen_digests[digest] = asset_id

        if not _is_decodable_image(Path(local_path)):
            items.append(
                ImageQCItem(
                    asset_id=asset_id,
                    uri=uri,
                    digest=digest,
                    score=0,
                    identity_score=0,
                    clarity_score=0,
                    usability_score=0,
                    verdict=QCVerdict.UNKNOWN,
                    eligible=False,
                    hard_failure=False,
                    reason="Image bytes are not decodable",
                )
            )
            continue

        try:
            res = validate_qc_response(evaluator.evaluate_image(
                image_path=local_path,
                prompt=prompt,
                system_instruction=IMAGE_QC_SYSTEM_PROMPT,
            ), QCStage.IMAGE)
            score = int(res.get("total_score", 0))
            identity_score = int(res.get("identity_score", 0))
            clarity_score = int(res.get("clarity_score", 0))
            usability_score = int(res.get("usability_score", 0))
            hard_failure = bool(res.get("hard_failure", False))
            raw_verdict = str(res.get("verdict", "fail")).lower()
            verdict = QCVerdict.PASS if raw_verdict == "pass" else (QCVerdict.UNKNOWN if raw_verdict == "unknown" else QCVerdict.FAIL)
            reason = str(res.get("reason", ""))

            # Enforce strict rubric logic:
            # Score >= 80, no hard failure, verdict == pass -> eligible
            eligible = bool(res["eligible"]) and (score >= 80) and (not hard_failure) and (verdict == QCVerdict.PASS)
            if hard_failure:
                eligible = False
                verdict = QCVerdict.FAIL

            items.append(
                ImageQCItem(
                    asset_id=asset_id,
                    uri=uri,
                    digest=digest,
                    score=score,
                    identity_score=identity_score,
                    clarity_score=clarity_score,
                    usability_score=usability_score,
                    verdict=verdict,
                    eligible=eligible,
                    hard_failure=hard_failure,
                    reason=reason,
                    findings=res,
                )
            )
        except Exception as exc:
            logger.error("Failed to evaluate image %s (%s): %s", asset_id, local_path, exc)
            diagnostics: dict[str, Any] = {}
            if isinstance(exc, QCResponseParseError):
                diagnostics = {
                    "raw_response": exc.raw_response,
                    "finish_reason": exc.finish_reason,
                    "parse_error": exc.parse_error,
                }
            items.append(
                ImageQCItem(
                    asset_id=asset_id,
                    uri=uri,
                    digest=digest,
                    score=0,
                    identity_score=0,
                    clarity_score=0,
                    usability_score=0,
                    verdict=QCVerdict.UNKNOWN,
                    eligible=False,
                    hard_failure=False,
                    reason=f"Evaluation call failed: {exc}",
                    findings=diagnostics,
                )
            )

    # 3. Aggregate overall result: must have >= 2 eligible assets to pass
    eligible_items = sorted(
        (it for it in items if it.eligible),
        key=lambda item: (
            -item.identity_score,
            -item.usability_score,
            -item.clarity_score,
            item.asset_id,
        ),
    )
    has_hard_fail_any = any(it.hard_failure for it in items)
    has_unknown = any(it.verdict == QCVerdict.UNKNOWN for it in items)

    if has_unknown and not has_hard_fail_any:
        overall_verdict = QCVerdict.UNKNOWN
        overall_score = round(sum(it.score for it in items) / len(items)) if items else 0
    elif len(eligible_items) >= 2:
        overall_verdict = QCVerdict.PASS
        overall_score = round(sum(it.score for it in eligible_items) / len(eligible_items))
    else:
        overall_verdict = QCVerdict.FAIL
        overall_score = round(sum(it.score for it in items) / len(items)) if items else 0

    recovery_actions = []
    if len(eligible_items) < 2:
        recovery_actions.append("reacquire_references")

    report_id = f"qc_img_{workflow_id}_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(timezone.utc).isoformat()
    findings = {
        "items": [it.to_dict() for it in items],
        "eligible_count": len(eligible_items),
        "total_count": len(items),
        "recovery_actions": recovery_actions,
        "recovery_reason": (
            f"Only {len(eligible_items)} eligible reference(s) available; minimum 2 required."
            if len(eligible_items) < 2
            else ""
        ),
        "eligible_reference_manifest": [
            {
                "asset_id": item.asset_id,
                "uri": item.uri,
                "sha256": item.digest,
                "eligible": True,
                "reference_rank": rank,
                "qc_score": item.score,
                "identity_score": item.identity_score,
                "clarity_score": item.clarity_score,
                "usability_score": item.usability_score,
                "view_angle": str(item.findings.get("view_angle") or ""),
                "shot_type": str(item.findings.get("shot_type") or ""),
                "visible_details": list(item.findings.get("visible_details") or []),
                "scene_suitability": list(item.findings.get("scene_suitability") or []),
                "risk_flags": list(item.findings.get("risk_flags") or []),
                "text_coverage_percent": int(item.findings.get("text_coverage_percent") or 0),
                "visual_observations": [
                    value
                    for value in (
                        str(item.findings.get("view_angle") or "").strip(),
                        str(item.findings.get("shot_type") or "").strip(),
                        *[str(value).strip() for value in item.findings.get("visible_details", [])],
                    )
                    if value
                ],
            }
            for rank, item in enumerate(eligible_items, start=1)
        ],
        "rejected_reference_manifest": [
            {
                "asset_id": item.asset_id,
                "uri": item.uri,
                "sha256": item.digest,
                "reason": item.reason,
                "hard_failure": item.hard_failure,
                "risk_flags": list(item.findings.get("risk_flags") or []),
            }
            for item in items
            if not item.eligible
        ],
        "product_evaluated": product.to_dict(),
        "automatic": True,
        "provider_mode": provider_mode,
        "model_identifier": model_identifier,
        "policy_version": IMAGE_POLICY_VERSION,
        "attempt_id": attempt_id,
    }

    report = QCReport(
        report_id=report_id,
        workflow_id=workflow_id,
        stage=QCStage.IMAGE,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        artifact_digest=artifact_digest,
        reference_digests=ref_digests,
        evaluator_name=evaluator_name,
        evaluator_version=evaluator_version,
        rubric_version=IMAGE_RUBRIC_VERSION,
        created_at=created_at,
        score=overall_score,
        verdict=overall_verdict,
        findings=findings,
        fingerprint=report_fingerprint,
        provider_mode=provider_mode,
        model_identifier=model_identifier,
        policy_version=IMAGE_POLICY_VERSION,
        owner_user_id=owner_user_id,
        project_id=project_id,
    )

    if repo is not None:
        repo.save_report(report)

    return report, eligible_items
