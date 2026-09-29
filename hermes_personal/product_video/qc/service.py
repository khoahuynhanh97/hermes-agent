"""Runtime entrypoint for governed Product Video QC."""

from __future__ import annotations

import json
import sqlite3
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_personal.product_video.qc.evaluator import MultimodalEvaluator
from hermes_personal.product_video.qc.image_qc import compute_artifact_digest, run_image_qc
from hermes_personal.product_video.qc.keyframe_qc import run_keyframe_qc
from hermes_personal.product_video.qc.models import QCStage, QCVerdict
from hermes_personal.product_video.qc.normalization import normalize_product_identity
from hermes_personal.product_video.qc.fingerprint import qc_fingerprint
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.qc.video_qc import compute_file_sha256, run_video_qc
from hermes_personal.workflows.budgets import BudgetPolicy, BudgetRepository
from hermes_personal.workflows.repository import WorkflowRepository


def _file_url_to_path(value: str | Path) -> Path:
    from hermes_personal.product_video.storage.layout import get_workspace_layout
    ws = get_workspace_layout()
    return ws.resolve_path(value)


def _reference_url_to_path(value: str | Path) -> Path:
    """Resolve approved external source images without widening video output paths."""
    from hermes_personal.product_video.storage.layout import (
        get_trusted_exchange_roots,
        get_workspace_layout,
    )

    return get_workspace_layout().resolve_path(
        value, allowed_roots=get_trusted_exchange_roots(),
    )


def _payload_dict(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not artifact:
        return {}
    payload = artifact.get("payload")
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
            return decoded if isinstance(decoded, dict) else {}
        except (TypeError, ValueError):
            return {}
    return payload if isinstance(payload, dict) else {}


class ProductVideoQCService:
    """Thin runtime adapter shared by operator CLI and future worker hooks."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        evaluator: Any | None = None,
        *,
        budget_policy: BudgetPolicy | None = None,
    ) -> None:
        self.connection = connection
        self.repository = QCReportRepository(connection)
        self.workflow_repository = WorkflowRepository(connection)
        self.evaluator = evaluator
        self.budget_repository = BudgetRepository(connection)
        self.budget_policy = budget_policy or BudgetPolicy(
            max_total=100_000,
            per_channel={"video_factory": 100_000},
            policy_id="product-video-qc",
            policy_version=1,
        )

    def run(
        self,
        workflow_id: str,
        stage: QCStage,
        *,
        provider_mode: str = "configured",
        authorize_cost: bool = False,
        max_cost_usd: float | None = None,
        authorization: dict[str, Any] | None = None,
        attempt_id: str | None = None,
        artifact_override: dict[str, Any] | None = None,
        storyboard_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if provider_mode not in ("configured", "fake"):
            raise ValueError("provider_mode must be 'configured' or 'fake'")
        if provider_mode == "configured" and (not authorize_cost or max_cost_usd is None or max_cost_usd <= 0):
            return {
                "status": "pending",
                "stage": stage.value,
                "reason": "Configured QC requires explicit cost authorization and a positive maximum budget",
            }

        workflow = self.workflow_repository.get_workflow(workflow_id)
        if workflow is None:
            return {"status": "failed", "stage": stage.value, "reason": f"Workflow '{workflow_id}' not found"}
        aggregate, _version = workflow
        source_context = aggregate.get("source_context") or {}

        owner_user_id = str(aggregate.get("owner_user_id") or source_context.get("owner_user_id") or "").strip()
        project_id = str(aggregate.get("project_id") or source_context.get("project_id") or "").strip()
        if not owner_user_id or not project_id:
            return {
                "status": "failed",
                "stage": stage.value,
                "reason": "Workflow aggregate is missing required owner_user_id or project_id",
            }

        def _authorization_terms() -> tuple[dict[str, Any] | None, str | None]:
            if provider_mode != "configured":
                return {}, None
            auth = authorization or {}
            if auth.get("workflow_id") != workflow_id:
                return None, "Cost authorization must bind to this workflow_id"
            authorization_id = str(auth.get("authorization_id") or auth.get("run_id") or "")
            if not authorization_id:
                return None, "Cost authorization is missing authorization_id"
            scope = auth.get("scope")
            scopes = scope if isinstance(scope, list) else [scope]
            if stage.value not in scopes and "product_video" not in scopes:
                return None, f"Cost authorization scope does not include {stage.value} QC"
            try:
                expires_at = datetime.fromisoformat(str(auth["expires_at"]).replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError):
                return None, "Cost authorization is missing a valid expires_at"
            if expires_at <= datetime.now(timezone.utc):
                return None, "Cost authorization has expired"
            try:
                workflow_max = int(float(auth.get("workflow_max_cost_usd", auth.get("max_cost_usd", 0))) * 100)
                campaign_max = int(float(auth.get("campaign_max_cost_usd", 100)) * 100)
            except (TypeError, ValueError):
                return None, "Cost authorization contains an invalid budget limit"
            if workflow_max <= 0 or campaign_max <= 0:
                return None, "Cost authorization maximums must be positive"
            return {
                "authorization_id": authorization_id,
                "campaign_id": str(auth.get("campaign_id") or "product-video-default"),
                "workflow_max": workflow_max,
                "campaign_max": campaign_max,
            }, None

        auth_terms, auth_error = _authorization_terms()
        if auth_error:
            return {"status": "pending", "stage": stage.value, "reason": auth_error}

        capability_id = f"product_video.qc.{stage.value}"

        def _backfill_legacy_attempts() -> None:
            if provider_mode != "configured" or not auth_terms:
                return
            authorization_id = auth_terms["authorization_id"]
            campaign_id = auth_terms["campaign_id"]
            # Existing reservations predate grant/attempt fields. Preserve and
            # attribute them; the live unknown report is therefore attempt 1.
            legacy_rows = self.connection.execute(
                """
                SELECT reservation_id, capability_id, operation_input_digest, amount, state, created_at
                FROM budget_reservation
                WHERE scope_id = ? AND external_reference = ?
                  AND (authorization_id = '' OR campaign_id = '' OR attempt_id = '')
                ORDER BY created_at, reservation_id
                """,
                (workflow_id, authorization_id),
            ).fetchall()
            for row in legacy_rows:
                legacy_capability = str(row["capability_id"])
                count = self.connection.execute(
                    """SELECT COUNT(*) FROM product_video_operation_attempt
                       WHERE authorization_id = ? AND workflow_id = ? AND capability_id = ?""",
                    (authorization_id, workflow_id, legacy_capability),
                ).fetchone()[0]
                legacy_attempt_id = f"legacy:{row['reservation_id']}"
                self.connection.execute(
                    """UPDATE budget_reservation
                       SET campaign_id = ?, authorization_id = ?, attempt_id = ?
                       WHERE reservation_id = ?""",
                    (campaign_id, authorization_id, legacy_attempt_id, row["reservation_id"]),
                )
                self.connection.execute(
                    """INSERT OR IGNORE INTO product_video_operation_attempt (
                         attempt_id, authorization_id, campaign_id, owner_user_id, workflow_id,
                         capability_id, attempt_number, input_fingerprint, estimated_cost,
                         reservation_id, status, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        legacy_attempt_id, authorization_id, campaign_id,
                        str(owner_user_id), workflow_id,
                        legacy_capability, count + 1, str(row["operation_input_digest"]),
                        int(row["amount"]), row["reservation_id"],
                        "technical_unknown" if legacy_capability == capability_id else str(row["state"]),
                        str(row["created_at"]), str(row["created_at"]),
                    ),
                )

        _backfill_legacy_attempts()

        def _next_attempt_id() -> tuple[str | None, int | None, str | None]:
            if provider_mode != "configured" or not auth_terms:
                return "", 0, None
            authorization_id = auth_terms["authorization_id"]
            rows = self.connection.execute(
                """SELECT attempt_number, status FROM product_video_operation_attempt
                   WHERE authorization_id = ? AND workflow_id = ? AND capability_id = ?
                   ORDER BY attempt_number DESC""",
                (authorization_id, workflow_id, capability_id),
            ).fetchall()
            if attempt_id:
                requested_number = len(rows) + 1
                return attempt_id, requested_number, None
            if len(rows) >= 3:
                return None, None, "QC maximum of 3 total attempts has been consumed"
            video_rework = False
            if stage == QCStage.VIDEO and rows and str(rows[0]["status"]) == "semantic_fail":
                retry_report_id = str(aggregate.get("video_retry_report_id") or "")
                previous_report = self.repository.get_report(retry_report_id) if retry_report_id else None
                current_render = aggregate.get("render_result") or {}
                current_digest = str(current_render.get("sha256") or "").removeprefix("sha256:")
                video_rework = bool(
                    aggregate.get("state") in {"rendering", "WaitingForOperator"}
                    and previous_report is not None
                    and previous_report.verdict == QCVerdict.FAIL
                    and previous_report.artifact_digest != current_digest
                    and current_digest
                )
            if rows and str(rows[0]["status"]) != "technical_unknown" and not (
                stage == QCStage.KEYFRAME
                and isinstance(aggregate.get("keyframe_recovery_plan"), dict)
                and aggregate.get("keyframe_recovery_plan", {}).get("frames")
            ) and not video_rework:
                return None, None, "Previous QC result is not a retryable technical UNKNOWN"
            number = len(rows) + 1
            return f"{authorization_id}:{stage.value}:{number}", number, None

        effective_attempt_id, attempt_number, attempt_error = _next_attempt_id()
        if attempt_error:
            return {"status": "pending", "stage": stage.value, "reason": attempt_error}

        def _admit(fingerprint: str) -> tuple[Any | None, dict[str, Any] | None]:
            completed = self.repository.claim(workflow_id, stage, fingerprint)
            if completed is not None:
                return None, {"status": "completed", "stage": stage.value, "report_id": completed.report_id, "report": completed}
            if provider_mode != "configured":
                return None, None
            amount_cents = max(1, math.ceil(float(max_cost_usd or 0) * 100))
            try:
                policy = BudgetPolicy(
                    max_total=int(auth_terms["workflow_max"]),
                    per_channel={"video_factory": int(auth_terms["workflow_max"])},
                    policy_id="product-video-workflow-cap",
                    policy_version=1,
                )
                allocation = self.budget_repository.reserve_budget(
                    policy,
                    "video_factory",
                    amount_cents,
                    idempotency_key=f"product-video-qc:{workflow_id}:{stage.value}:{fingerprint}",
                    owner_user_id=str(aggregate.get("owner_user_id") or "default-owner"),
                    scope_id=workflow_id,
                    capability_id=capability_id,
                    operation_input_digest=fingerprint,
                    external_reference=auth_terms["authorization_id"],
                    campaign_id=auth_terms["campaign_id"],
                    campaign_max=int(auth_terms["campaign_max"]),
                    authorization_id=auth_terms["authorization_id"],
                    attempt_id=str(effective_attempt_id),
                )
                now = datetime.now(timezone.utc).isoformat()
                self.connection.execute(
                    """INSERT OR IGNORE INTO product_video_operation_attempt (
                         attempt_id, authorization_id, campaign_id, owner_user_id, workflow_id,
                         capability_id, attempt_number, input_fingerprint, estimated_cost,
                         reservation_id, status, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)""",
                    (
                        str(effective_attempt_id), auth_terms["authorization_id"], auth_terms["campaign_id"],
                        str(aggregate.get("owner_user_id") or "default-owner"), workflow_id, capability_id,
                        int(attempt_number or 0), fingerprint, amount_cents, allocation.reservation_id, now, now,
                    ),
                )
                return allocation, None
            except Exception as exc:
                self.repository.release_claim(workflow_id, stage, fingerprint)
                return None, {
                    "status": "pending",
                    "stage": stage.value,
                    "reason": f"Budget admission denied before evaluator call: {exc}",
                }

        def _finish(fingerprint: str, report: Any, allocation: Any | None) -> dict[str, Any]:
            self.repository.complete_claim(workflow_id, stage, fingerprint, report.report_id)
            if allocation is not None:
                outcome = "pass" if getattr(report.verdict, "value", report.verdict) == "pass" else "semantic_fail"
                if stage == QCStage.KEYFRAME and outcome == "semantic_fail":
                    package = artifact_override or aggregate.get("storyboard") or {}
                    frames = package.get("generated_keyframes", []) if isinstance(package, dict) else []
                    provider_incomplete = any(
                        not isinstance(item, dict)
                        or str(item.get("status", "")).lower() != "completed"
                        or not item.get("image_path")
                        for item in frames
                    )
                    if provider_incomplete:
                        outcome = "technical_unknown"
                if getattr(report.verdict, "value", report.verdict) == "unknown":
                    items = report.findings.get("items", []) if isinstance(report.findings, dict) else []
                    technical = any(
                        bool(item.get("findings", {}).get("parse_error"))
                        or (
                            str(item.get("verdict", "")).lower() == "unknown"
                            and str(item.get("reason", "")).startswith("Evaluation call failed:")
                        )
                        for item in items
                        if isinstance(item, dict)
                    )
                    outcome = "technical_unknown" if technical else "unknown"
                # A disabled Vertex service rejects every image before inference.
                # Keep the failed attempt and QC report, but do not charge its
                # reserved ceiling against later stages of the same workflow.
                items = report.findings.get("items", []) if isinstance(report.findings, dict) else []
                service_disabled = (
                    stage == QCStage.IMAGE
                    and outcome == "technical_unknown"
                    and bool(items)
                    and all(
                        isinstance(item, dict)
                        and "MultimodalEvaluator HTTP 403:" in str(item.get("reason", ""))
                        and "SERVICE_DISABLED" in str(item.get("reason", ""))
                        for item in items
                    )
                )
                if service_disabled:
                    self.budget_repository.release_budget(allocation)
                else:
                    self.budget_repository.commit_budget(allocation)
                with self.connection:
                    self.connection.execute(
                        """UPDATE product_video_operation_attempt SET status = ?, updated_at = ? WHERE attempt_id = ?""",
                        (outcome, datetime.now(timezone.utc).isoformat(), str(effective_attempt_id)),
                    )
            result = {
                "status": "completed",
                "stage": stage.value,
                "report_id": report.report_id,
                "report": report,
            }
            if allocation is not None:
                result["budget_reservation_id"] = allocation.reservation_id
                result["reserved_cost_usd"] = allocation.amount / 100
            return result

        if stage == QCStage.IMAGE:
            artifact = artifact_override or aggregate.get("resource_pack") or {}
            if not artifact:
                return {"status": "unknown", "stage": stage.value, "reason": "Durable resource_pack artifact is missing"}
            product = normalize_product_identity(artifact, source_context=source_context)
            evaluator = self.evaluator or MultimodalEvaluator(fake_mode=provider_mode == "fake")
            artifact_digest = compute_artifact_digest(artifact)
            fingerprint = qc_fingerprint(
                workflow_id,
                stage,
                artifact_digest,
                product,
                evaluator_name=str(getattr(evaluator, "evaluator_name", "unknown")),
                evaluator_version=str(getattr(evaluator, "evaluator_version", "unknown")),
                model_identifier=str(getattr(evaluator, "model", "")),
                attempt_id=str(effective_attempt_id),
            )
            allocation, completed = _admit(fingerprint)
            if completed:
                return completed
            report, eligible = run_image_qc(
                workflow_id,
                artifact,
                product,
                evaluator=evaluator,
                repo=self.repository,
                attempt_id=str(effective_attempt_id),
                owner_user_id=owner_user_id,
                project_id=project_id,
            )
            result = _finish(fingerprint, report, allocation)
            result["eligible_count"] = len(eligible)
            return result

        if stage == QCStage.KEYFRAME:
            package = artifact_override or aggregate.get("storyboard") or {}
            if not isinstance(package, dict) or not package.get("generated_keyframes"):
                return {
                    "status": "unknown",
                    "stage": stage.value,
                    "reason": "Durable generated keyframe package is missing",
                }
            pack = aggregate.get("resource_pack") or {}
            product = normalize_product_identity(pack, source_context=source_context)
            
            # Fail-closed: never backfill missing digest from current disk bytes
            package_digest = str(package.get("package_digest") or "").strip()
            if not package_digest:
                return {
                    "status": "failed",
                    "stage": stage.value,
                    "reason": "Keyframe package is missing required package_digest; cannot compute from current disk state",
                }
            artifact_digest = package_digest
            evaluator = self.evaluator or MultimodalEvaluator(fake_mode=provider_mode == "fake")
            fingerprint = qc_fingerprint(
                workflow_id,
                stage,
                artifact_digest,
                product,
                evaluator_name=str(getattr(evaluator, "evaluator_name", "unknown")),
                evaluator_version=str(getattr(evaluator, "evaluator_version", "unknown")),
                model_identifier=str(getattr(evaluator, "model", "")),
                storyboard=package,
                reference_digests=[
                    compute_file_sha256(_reference_url_to_path(path))
                    for item in package.get("generated_keyframes", [])
                    if isinstance(item, dict)
                    for path in item.get("reference_image_paths", [])
                ],
                attempt_id=str(effective_attempt_id),
            )
            allocation, completed = _admit(fingerprint)
            if completed:
                return completed
            report = run_keyframe_qc(
                workflow_id=workflow_id,
                package=package,
                product=product,
                evaluator=evaluator,
                repo=self.repository,
                attempt_id=str(effective_attempt_id),
                owner_user_id=owner_user_id,
                project_id=project_id,
            )
            return _finish(fingerprint, report, allocation)

        render_artifact = artifact_override or aggregate.get("render_result") or {}
        required_render_lineage = (
            "owner_user_id",
            "project_id",
            "workflow_id",
            "artifact_id",
            "artifact_version",
            "sha256",
        )
        missing_render_lineage = [
            field
            for field in required_render_lineage
            if field not in render_artifact
            or render_artifact[field] is None
            or (
                isinstance(render_artifact[field], str)
                and not render_artifact[field].strip()
            )
        ]
        if missing_render_lineage:
            return {
                "status": "failed",
                "stage": stage.value,
                "reason": "Render artifact is missing canonical lineage fields: "
                + ", ".join(missing_render_lineage),
            }

        render_owner = str(render_artifact["owner_user_id"]).strip()
        render_project = str(render_artifact["project_id"]).strip()
        render_workflow = str(render_artifact["workflow_id"]).strip()
        artifact_id = str(render_artifact["artifact_id"]).strip()
        if render_owner != owner_user_id:
            return {
                "status": "failed",
                "stage": stage.value,
                "reason": "Render owner_user_id does not match workflow owner_user_id",
            }
        if render_project != project_id:
            return {
                "status": "failed",
                "stage": stage.value,
                "reason": "Render project_id does not match workflow project_id",
            }
        if render_workflow != workflow_id:
            return {
                "status": "failed",
                "stage": stage.value,
                "reason": "Render workflow_id does not match the workflow being evaluated",
            }

        render_ver_raw = render_artifact["artifact_version"]
        if (
            isinstance(render_ver_raw, bool)
            or not isinstance(render_ver_raw, int)
            or render_ver_raw < 1
        ):
            return {
                "status": "failed",
                "stage": stage.value,
                "reason": "Render artifact_version must be a positive integer",
            }
        render_ver = render_ver_raw
        compatibility_version = render_artifact.get("version")
        if compatibility_version is not None and compatibility_version != render_ver:
            return {
                "status": "failed",
                "stage": stage.value,
                "reason": "Render version does not match artifact_version",
            }

        expected_sha = (
            str(render_artifact["sha256"])
            .strip()
            .removeprefix("sha256:")
            .lower()
        )
        if len(expected_sha) != 64 or any(
            ch not in "0123456789abcdef" for ch in expected_sha
        ):
            return {
                "status": "failed",
                "stage": stage.value,
                "reason": "Render sha256 must be a canonical 64-character hexadecimal digest",
            }

        storyboard = storyboard_override or aggregate.get("storyboard") or {}
        storyboard = _payload_dict(storyboard) or storyboard
        if isinstance(storyboard, dict):
            # Scene plan is the durable source for approved boundaries when a
            # renderer stores only the frame prompts in its storyboard output.
            scene_plan = _payload_dict(aggregate.get("scene_plan") or {})
            if not (storyboard.get("scene_boundaries") or storyboard.get("scenes")):
                plan_scenes = scene_plan.get("scene_boundaries") or scene_plan.get("scenes")
                if isinstance(plan_scenes, list) and plan_scenes:
                    storyboard = dict(storyboard)
                    storyboard["scene_boundaries"] = plan_scenes
            if not storyboard.get("frames") and isinstance(storyboard.get("scenes"), list):
                storyboard = dict(storyboard)
                storyboard["frames"] = [
                    {
                        "description": scene.get("visual_objective") or scene.get("subject_action") or "",
                        "duration_seconds": scene.get("duration_seconds"),
                    }
                    for scene in storyboard["scenes"]
                    if isinstance(scene, dict)
                ]
        video_value = (
            render_artifact.get("file_path")
            or render_artifact.get("video_url")
            or render_artifact.get("final_video_url")
            or render_artifact.get("output_url")
        )
        if not video_value:
            return {"status": "unknown", "stage": stage.value, "reason": "Current render has no local video output"}
        if not storyboard:
            return {"status": "unknown", "stage": stage.value, "reason": "Approved storyboard is missing from workflow aggregate"}

        pack = aggregate.get("resource_pack") or {}
        product = normalize_product_identity(pack, source_context=source_context)
        image_digest = compute_artifact_digest(pack)
        image_report = self.repository.get_latest_report(
            workflow_id,
            QCStage.IMAGE,
            expected_artifact_digest=image_digest,
        )
        if image_report is None or image_report.verdict.value != "pass":
            return {"status": "pending", "stage": stage.value, "reason": "Current image QC PASS is required before video QC"}
        reference_manifest = image_report.findings.get("eligible_reference_manifest", [])
        if not isinstance(reference_manifest, list) or not reference_manifest:
            reference_manifest = image_report.findings.get("items", [])
        approved_paths = []
        for item in reference_manifest if isinstance(reference_manifest, list) else []:
            if not isinstance(item, dict) or not item.get("eligible"):
                continue
            reference_value = item.get("local_path") or item.get("uri") or item.get("path")
            if reference_value:
                approved_paths.append(_reference_url_to_path(reference_value))
        if len(approved_paths) < 2 or any(not path.is_file() for path in approved_paths):
            return {"status": "unknown", "stage": stage.value, "reason": "Current image QC has no usable eligible reference manifest"}
        evaluator = self.evaluator or MultimodalEvaluator(fake_mode=provider_mode == "fake")
        duration_value = render_artifact.get("duration_seconds")
        if duration_value is None and isinstance(storyboard, dict):
            boundaries = storyboard.get("scene_boundaries") or storyboard.get("scenes") or []
            durations: list[float] = []
            for boundary in boundaries if isinstance(boundaries, list) else []:
                if not isinstance(boundary, dict):
                    continue
                try:
                    if boundary.get("duration_seconds") is not None:
                        durations.append(float(boundary["duration_seconds"]))
                    elif boundary.get("start_seconds") is not None and boundary.get("end_seconds") is not None:
                        durations.append(float(boundary["end_seconds"]) - float(boundary["start_seconds"]))
                except (TypeError, ValueError):
                    durations = []
                    break
            duration_value = sum(durations) if durations and all(value > 0 for value in durations) else 16.0
        expected_duration = float(duration_value or 16.0)
        video_path = _file_url_to_path(video_value)
        video_sha = compute_file_sha256(video_path)

        if video_sha != expected_sha:
            return {
                "status": "failed",
                "stage": stage.value,
                "reason": f"Render artifact SHA ({expected_sha}) does not match video on disk ({video_sha})",
            }

        render_payload = _payload_dict(render_artifact)
        raw_scene_providers = render_payload.get("scene_provider_kinds")
        scene_provider_kinds = (
            raw_scene_providers
            if isinstance(raw_scene_providers, list)
            and render_payload.get("artifact_id") == artifact_id
            and str(render_payload.get("sha256") or "").removeprefix("sha256:") == video_sha
            and render_payload.get("render_id") == render_artifact.get("render_id")
            and all(kind in {"google_flow", "vertex_ai"} for kind in raw_scene_providers)
            else []
        )

        fingerprint = qc_fingerprint(
            workflow_id,
            stage,
            video_sha,
            product,
            evaluator_name=str(getattr(evaluator, "evaluator_name", "unknown")),
            evaluator_version=str(getattr(evaluator, "evaluator_version", "unknown")),
            model_identifier=str(getattr(evaluator, "model", "")),
            storyboard=storyboard,
            video_sha256=video_sha,
            reference_digests=[compute_file_sha256(path) for path in approved_paths],
            attempt_id=str(effective_attempt_id),
            scene_provider_kinds=scene_provider_kinds,
        )
        allocation, completed = _admit(fingerprint)
        if completed:
            return completed
        report = run_video_qc(
            workflow_id,
            video_path,
            storyboard,
            product,
            approved_paths,
            expected_duration=expected_duration,
            evaluator=evaluator,
            repo=self.repository,
            attempt_id=str(effective_attempt_id),
            owner_user_id=owner_user_id,
            project_id=project_id,
            artifact_id=artifact_id,
            artifact_version=render_ver,
            scene_provider_kinds=scene_provider_kinds,
        )
        result = _finish(fingerprint, report, allocation)
        result["video_sha256"] = video_sha
        return result
