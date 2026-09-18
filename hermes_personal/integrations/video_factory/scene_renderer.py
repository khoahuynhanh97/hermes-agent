"""Grounded, resumable video-scene compilation and paid-operation checkpoints."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

from .ports import VideoGenerationPort, VideoGenerationRequest, VideoGenerationResult
from .scene_validator import validate_scene_output


SUPPORTED_SCENE_DURATIONS = frozenset({4, 6, 8})
MANDATORY_VIDEO_NEGATIVE_PROMPT = (
    "readable text, captions, subtitles, watermark, seller name, shop name, store logo, "
    "marketplace UI, price tag, rating badge, social handle, shipping label, unrelated brand "
    "mark, source-store branding, malformed product, changed logo, changed product "
    "shape, changed port placement, changed display shape, wrong variant, duplicate product, "
    "duplicated product, extra product, malformed hands, malformed cables, cable entering screen, "
    "cable entering forbidden region, unrelated accessories, black bars, letterboxing, square composition, "
    "static pan, static zoom, slideshow"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _merge_negative_prompt(value: Any) -> str:
    chunks = [str(value or ""), MANDATORY_VIDEO_NEGATIVE_PROMPT]
    seen: set[str] = set()
    result: list[str] = []
    for item in ",".join(chunks).split(","):
        normalized = item.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return ", ".join(result)


def _validate_keyframe_receipt(
    *,
    keyframe: dict[str, Any],
    receipt: dict[str, Any],
    package_digest: str,
) -> None:
    if receipt.get("stage") != "keyframe" or receipt.get("verdict") != "pass":
        raise ValueError("generated keyframe requires a Keyframe QC PASS receipt")
    if int(receipt.get("score") or 0) < 80:
        raise ValueError("generated keyframe QC score must be at least 80")
    if bool(receipt.get("hard_failure")):
        raise ValueError("generated keyframe QC receipt contains a hard failure")
    if str(receipt.get("artifact_digest") or "") != package_digest:
        raise ValueError("keyframe QC artifact digest does not match the approved package digest")

    findings = receipt.get("findings") if isinstance(receipt.get("findings"), dict) else {}
    items = findings.get("items") if isinstance(findings.get("items"), list) else []
    frame_id = str(keyframe.get("frame_id") or "")
    item = next(
        (
            value
            for value in items
            if isinstance(value, dict) and str(value.get("frame_id") or "") == frame_id
        ),
        None,
    )
    if item is None:
        raise ValueError(f"keyframe QC receipt has no binding for frame {frame_id!r}")
    if (
        item.get("verdict") != "pass"
        or bool(item.get("hard_failure"))
        or int(item.get("score") or 0) < 80
    ):
        raise ValueError(f"keyframe {frame_id!r} did not pass QC with score at least 80")

    expected_sha = str(keyframe.get("sha256") or "").removeprefix("sha256:")
    item_sha = str(item.get("sha256") or "").removeprefix("sha256:")
    if not expected_sha or item_sha != expected_sha:
        raise ValueError(f"keyframe QC SHA-256 binding mismatch for frame {frame_id!r}")
    references = sorted(
        str(value).removeprefix("sha256:")
        for value in keyframe.get("reference_sha256s", [])
        if value
    )
    qc_references = sorted(
        str(value).removeprefix("sha256:")
        for value in item.get("reference_digests", [])
        if value
    )
    if not references or qc_references != references:
        raise ValueError(f"keyframe QC reference binding mismatch for frame {frame_id!r}")


def compile_grounded_scene_request(
    *,
    owner_user_id: str,
    workflow_id: str,
    project_id: str,
    scene: dict[str, Any],
    keyframe: dict[str, Any],
    keyframe_qc_receipt: dict[str, Any],
    package_digest: str,
    product_identity: str,
    provider_model: str,
    aspect_ratio: str = "9:16",
    provider_options: dict[str, Any] | None = None,
) -> VideoGenerationRequest:
    """Compile one approved scene without leaking overlay copy to the video model."""
    scene_id = str(scene.get("scene_id") or "").strip()
    if not scene_id:
        raise ValueError("scene_id is required")
    duration = int(scene.get("duration_seconds") or 0)
    if duration not in SUPPORTED_SCENE_DURATIONS:
        raise ValueError(
            f"{scene_id} requests {duration}s; allowed values are 4, 6, 8"
        )
    required = (
        "subject_action",
        "product_interaction",
        "start_state",
        "end_state",
        "visual_change",
        "environment",
    )
    missing = [name for name in required if not str(scene.get(name) or "").strip()]
    if missing:
        raise ValueError(f"{scene_id} is missing grounded scene fields: {', '.join(missing)}")

    subject_action = str(scene["subject_action"]).strip()
    camera_only = subject_action.casefold().strip(" .") in {
        "zoom in",
        "zoom out",
        "pan left",
        "pan right",
        "rotate product",
        "show product",
        "demonstrate product",
    }
    if camera_only:
        raise ValueError(f"{scene_id} subject_action must describe a physical action")

    if str(keyframe.get("scene_id") or "") != scene_id:
        raise ValueError("generated keyframe scene binding mismatch")
    _validate_keyframe_receipt(
        keyframe=keyframe,
        receipt=keyframe_qc_receipt,
        package_digest=package_digest,
    )
    keyframe_path = Path(str(keyframe.get("image_path") or "")).resolve()
    expected_sha = str(keyframe.get("sha256") or "").removeprefix("sha256:")
    if (
        not keyframe_path.is_file()
        or keyframe_path.stat().st_size == 0
        or _sha256(keyframe_path) != expected_sha
    ):
        raise ValueError("generated keyframe is missing, empty, or changed after QC")

    if not workflow_id.strip():
        raise ValueError("workflow_id is required for deterministic scene operation identity")
    operation_material = (
        f"{workflow_id}|{scene_id}|{package_digest}|{provider_model}|{duration}"
    )
    operation_id = "video-scene-" + hashlib.sha256(
        operation_material.encode()
    ).hexdigest()[:24]
    interaction_pieces = []
    if scene.get("interaction_actor"):
        interaction_pieces.append(f"Interaction actor: {str(scene['interaction_actor']).strip()}")
    if scene.get("interaction_target"):
        interaction_pieces.append(f"Interaction target: {str(scene['interaction_target']).strip()}")
    if scene.get("contact_landmark"):
        interaction_pieces.append(f"Contact landmark: {str(scene['contact_landmark']).strip()}")
    if scene.get("approach_vector"):
        interaction_pieces.append(f"Approach vector: {str(scene['approach_vector']).strip()}")
    if scene.get("object_orientation"):
        interaction_pieces.append(f"Object orientation: {str(scene['object_orientation']).strip()}")
    forbidden = scene.get("forbidden_contact_regions", [])
    if forbidden:
        interaction_pieces.append(f"FORBIDDEN contact regions (do NOT touch or insert into): {', '.join(str(f) for f in forbidden)}")
    interaction_block = (". ".join(interaction_pieces) + ".") if interaction_pieces else ""

    prompt_parts = [
        f"Create a product-grounded vertical video scene for {product_identity}.",
        f"Subject action: {subject_action}.",
        f"Product interaction: {str(scene['product_interaction']).strip()}.",
    ]
    if interaction_block:
        prompt_parts.append(interaction_block)
    prompt_parts.extend([
        f"Exact start state: {str(scene['start_state']).strip()}.",
        f"Exact end state: {str(scene['end_state']).strip()}.",
        f"Required visible change: {str(scene['visual_change']).strip()}.",
        f"Environment: {str(scene['environment']).strip()}.",
        f"Camera framing: {str(scene.get('camera_framing') or 'product-focused medium close-up').strip()}.",
        f"Camera movement: {str(scene.get('camera_movement') or 'subtle action-following movement').strip()}.",
        f"Product placement: {str(scene.get('product_placement') or 'keep the approved product fully visible and unobstructed').strip()}.",
        f"Lighting: {str(scene.get('lighting') or 'preserve true product color and material').strip()}.",
        f"Continuity from prior scene: {str(scene.get('continuity_from_previous') or 'preserve the same approved product unit').strip()}.",
        f"Continuity into next scene: {str(scene.get('continuity_to_next') or 'keep identity, placement and orientation stable').strip()}.",
        "Required identity cues: "
        + ", ".join(str(value) for value in scene.get("product_identity_cues", []))
        + ".",
        "Required visible details: "
        + ", ".join(str(value) for value in scene.get("required_visible_details", []))
        + ".",
        "Preserve the approved product identity, exact model and variant, proportions, color, material, controls, logo placement and distinctive details.",
        "Animate the physical action and state transition; do not create a static pan, zoom, rotation or slideshow.",
        "Use the approved keyframe as the exact visual start state; do not redesign, replace, multiply or morph the product.",
        "Do not render any readable text, captions, watermark, marketplace UI, seller branding or unrelated logo.",
    ])
    prompt = " ".join(part for part in prompt_parts if part)
    options = dict(provider_options or {})
    options["negativePrompt"] = _merge_negative_prompt(options.get("negativePrompt"))
    options["approved_keyframe"] = {
        "frame_id": keyframe.get("frame_id"),
        "sha256": expected_sha,
        "package_digest": package_digest,
        "qc_report_id": keyframe_qc_receipt.get("report_id"),
    }
    return VideoGenerationRequest(
        request_id=operation_id,
        owner_user_id=owner_user_id,
        project_id=project_id,
        scene_id=scene_id,
        prompt=prompt,
        duration_seconds=duration,
        reference_image_paths=(str(keyframe_path),),
        aspect_ratio=aspect_ratio,
        provider_options=options,
    )


def stable_scene_request_digest(request: VideoGenerationRequest) -> str:
    references = []
    for raw_path in request.reference_image_paths:
        path = Path(raw_path).resolve()
        references.append(
            {
                "path": str(path),
                "sha256": _sha256(path) if path.is_file() else "",
            }
        )
    payload = {
        "request_id": request.request_id,
        "owner_user_id": request.owner_user_id,
        "project_id": request.project_id,
        "scene_id": request.scene_id,
        "prompt": request.prompt,
        "duration_seconds": request.duration_seconds,
        "reference_images": references,
        "aspect_ratio": request.aspect_ratio,
        "provider_options": request.provider_options,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class SceneRenderOperationStore:
    DDL = """
    CREATE TABLE IF NOT EXISTS video_factory_scene_operation (
        operation_id TEXT PRIMARY KEY,
        owner_user_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        scene_id TEXT NOT NULL,
        request_digest TEXT NOT NULL,
        provider_operation_id TEXT,
        status TEXT NOT NULL,
        output_path TEXT,
        output_sha256 TEXT NOT NULL DEFAULT '',
        error_code TEXT NOT NULL DEFAULT '',
        error_message TEXT NOT NULL DEFAULT '',
        render_batch_id TEXT NOT NULL DEFAULT '',
        scene_order INTEGER NOT NULL DEFAULT 0,
        attempt INTEGER NOT NULL DEFAULT 1,
        artifact_id TEXT NOT NULL DEFAULT '',
        expected_duration_seconds REAL NOT NULL DEFAULT 0,
        expected_aspect_ratio TEXT NOT NULL DEFAULT '9:16',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_vf_scene_op_batch ON video_factory_scene_operation(render_batch_id, scene_order);
    """

    def __init__(self, connection: sqlite3.Connection | str | Path) -> None:
        if isinstance(connection, (str, Path)):
            self.connection = sqlite3.connect(str(connection))
            self._owns_connection = True
        else:
            self.connection = connection
            self._owns_connection = False
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(self.DDL)
        self._ensure_migrations()

    def _ensure_migrations(self) -> None:
        cur = self.connection.execute("PRAGMA table_info(video_factory_scene_operation)")
        cols = {r[1] for r in cur.fetchall()}
        migrations = {
            "render_batch_id": "ALTER TABLE video_factory_scene_operation ADD COLUMN render_batch_id TEXT NOT NULL DEFAULT ''",
            "scene_order": "ALTER TABLE video_factory_scene_operation ADD COLUMN scene_order INTEGER NOT NULL DEFAULT 0",
            "attempt": "ALTER TABLE video_factory_scene_operation ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1",
            "artifact_id": "ALTER TABLE video_factory_scene_operation ADD COLUMN artifact_id TEXT NOT NULL DEFAULT ''",
            "expected_duration_seconds": "ALTER TABLE video_factory_scene_operation ADD COLUMN expected_duration_seconds REAL NOT NULL DEFAULT 0",
            "expected_aspect_ratio": "ALTER TABLE video_factory_scene_operation ADD COLUMN expected_aspect_ratio TEXT NOT NULL DEFAULT '9:16'",
        }
        for col_name, stmt in migrations.items():
            if col_name not in cols:
                self.connection.execute(stmt)
        self.connection.executescript("CREATE INDEX IF NOT EXISTS idx_vf_scene_op_batch ON video_factory_scene_operation(render_batch_id, scene_order)")

    def get(self, operation_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM video_factory_scene_operation WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return dict(row) if row else None

    def mark_planned(self, request: VideoGenerationRequest, render_batch_id: str = "", scene_order: int = 0) -> None:
        """Insert-only or compare-and-set planning record; never regresses submitting/running/completed states."""
        digest = stable_scene_request_digest(request)
        existing = self.get(request.request_id)
        if existing:
            if existing["request_digest"] != digest:
                raise ValueError("video scene operation idempotency conflict")
            # If already in submitting, submitted, running, completed, or failed, never regress to planned
            if existing["status"] in ("submitting", "submitted", "running", "completed", "failed"):
                return
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO video_factory_scene_operation (
                    operation_id, owner_user_id, project_id, scene_id,
                    request_digest, provider_operation_id, status, output_path,
                    output_sha256, error_code, error_message, render_batch_id, scene_order,
                    expected_duration_seconds, expected_aspect_ratio, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, 'planned', NULL, '', '', '', ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(operation_id) DO UPDATE SET
                    render_batch_id = CASE WHEN video_factory_scene_operation.render_batch_id = '' THEN excluded.render_batch_id ELSE video_factory_scene_operation.render_batch_id END,
                    scene_order = CASE WHEN video_factory_scene_operation.scene_order = 0 THEN excluded.scene_order ELSE video_factory_scene_operation.scene_order END,
                    expected_duration_seconds = CASE WHEN video_factory_scene_operation.expected_duration_seconds = 0 THEN excluded.expected_duration_seconds ELSE video_factory_scene_operation.expected_duration_seconds END,
                    expected_aspect_ratio = CASE WHEN video_factory_scene_operation.expected_aspect_ratio = '9:16' AND video_factory_scene_operation.status = 'planned' THEN excluded.expected_aspect_ratio ELSE video_factory_scene_operation.expected_aspect_ratio END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE video_factory_scene_operation.status = 'planned'
                """,
                (
                    request.request_id,
                    request.owner_user_id,
                    request.project_id,
                    request.scene_id,
                    digest,
                    render_batch_id,
                    scene_order,
                    float(request.duration_seconds),
                    request.aspect_ratio,
                ),
            )

    def mark_submitting(self, request: VideoGenerationRequest) -> bool:
        """Atomic compare-and-set transition to submitting."""
        digest = stable_scene_request_digest(request)
        existing = self.get(request.request_id)
        if existing and existing["request_digest"] != digest:
            raise ValueError("video scene operation idempotency conflict")
        with self.connection:
            cur = self.connection.execute(
                """
                INSERT INTO video_factory_scene_operation (
                    operation_id, owner_user_id, project_id, scene_id,
                    request_digest, provider_operation_id, status, output_path,
                    output_sha256, error_code, error_message, render_batch_id, scene_order,
                    expected_duration_seconds, expected_aspect_ratio, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, 'submitting', NULL, '', 'SUBMISSION_NOT_RECONCILED', 'provider submission started without a durable provider operation id', '', 0, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(operation_id) DO UPDATE SET
                    status = 'submitting',
                    error_code = 'SUBMISSION_NOT_RECONCILED',
                    error_message = 'provider submission started without a durable provider operation id',
                    expected_duration_seconds = CASE WHEN video_factory_scene_operation.expected_duration_seconds = 0 THEN excluded.expected_duration_seconds ELSE video_factory_scene_operation.expected_duration_seconds END,
                    expected_aspect_ratio = CASE WHEN video_factory_scene_operation.expected_aspect_ratio = '9:16' AND video_factory_scene_operation.status = 'planned' THEN excluded.expected_aspect_ratio ELSE video_factory_scene_operation.expected_aspect_ratio END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE video_factory_scene_operation.status = 'planned'
                """,
                (
                    request.request_id,
                    request.owner_user_id,
                    request.project_id,
                    request.scene_id,
                    digest,
                    float(request.duration_seconds),
                    request.aspect_ratio,
                ),
            )
            return cur.rowcount > 0

    def finalize_provider_result(
        self,
        operation_id: str,
        result: VideoGenerationResult,
    ) -> dict[str, Any]:
        """Validate a provider result and CAS the durable operation state.
        
        Returns the final operation state after validation and transition.
        """
        existing = self.get(operation_id)
        if not existing:
            raise ValueError(f"Operation {operation_id} not found")
        
        # Verify provider operation ID consistency
        if existing["provider_operation_id"]:
            if result.provider_operation_id and result.provider_operation_id != existing["provider_operation_id"]:
                raise ValueError("provider_operation_id mismatch")
        
        # Terminal states cannot be regressed
        if existing["status"] in ("completed", "failed"):
            return dict(existing)
        
        # Check validation contract
        expected_duration = float(existing.get("expected_duration_seconds") or 0)
        expected_aspect = str(existing.get("expected_aspect_ratio") or "")
        
        if expected_duration <= 0 or not expected_aspect:
            # Missing validation contract - fail closed
            with self.connection:
                self.connection.execute(
                    """
                    UPDATE video_factory_scene_operation
                    SET status = 'failed',
                        error_code = 'VALIDATION_CONTRACT_MISSING',
                        error_message = 'Operation missing expected_duration_seconds or expected_aspect_ratio',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE operation_id = ? AND status NOT IN ('completed', 'failed')
                    """,
                    (operation_id,),
                )
            return dict(self.get(operation_id) or existing)
        
        # Validate provider output before marking completed
        output_sha = ""
        final_status = result.status
        error_code = result.error_code or ""
        error_message = result.error_message or ""
        
        if result.status == "completed" and result.video_path:
            try:
                validation = validate_scene_output(
                    output_path=result.video_path,
                    expected_duration=expected_duration,
                    expected_aspect_ratio=expected_aspect,
                    duration_tolerance=0.5,
                )
                output_sha = validation.sha256
            except ValueError as exc:
                # Validation failed - transition to failed state
                final_status = "failed"
                error_code = "VALIDATION_FAILED"
                error_message = str(exc)
                output_sha = ""
        elif result.video_path:
            path = Path(result.video_path)
            if path.is_file() and path.stat().st_size > 0:
                output_sha = _sha256(path)
        
        with self.connection:
            self.connection.execute(
                """
                UPDATE video_factory_scene_operation
                SET status = ?,
                    provider_operation_id = COALESCE(?, video_factory_scene_operation.provider_operation_id),
                    output_path = COALESCE(?, video_factory_scene_operation.output_path),
                    output_sha256 = CASE WHEN ? != '' THEN ? ELSE video_factory_scene_operation.output_sha256 END,
                    error_code = ?,
                    error_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE operation_id = ?
                  AND status NOT IN ('completed', 'failed')
                """,
                (
                    final_status,
                    result.provider_operation_id,
                    result.video_path,
                    output_sha,
                    output_sha,
                    error_code,
                    error_message,
                    operation_id,
                ),
            )
        
        return dict(self.get(operation_id) or existing)

    def save_result(
        self, request: VideoGenerationRequest, result: VideoGenerationResult
    ) -> None:
        """Atomically persist provider response, enforcing monotonic state transitions."""
        digest = stable_scene_request_digest(request)
        existing = self.get(request.request_id)
        if existing:
            if existing["request_digest"] != digest:
                raise ValueError("video scene operation idempotency conflict")
            if (
                existing["provider_operation_id"]
                and result.provider_operation_id
                and existing["provider_operation_id"] != result.provider_operation_id
            ):
                raise ValueError("provider_operation_id mismatch")
            current_status = existing["status"]
            # Terminal states can never be regressed
            if current_status in ("completed", "failed"):
                return
            if current_status == "running" and result.status not in ("running", "completed", "failed"):
                return

        # Validate provider output before marking completed
        output_sha = ""
        if result.status == "completed" and result.video_path:
            try:
                validation = validate_scene_output(
                    output_path=result.video_path,
                    expected_duration=request.duration_seconds,
                    expected_aspect_ratio=request.aspect_ratio,
                    duration_tolerance=0.5,
                )
                output_sha = validation.sha256
            except ValueError as exc:
                # Validation failed - transition to failed state instead
                result = replace(
                    result,
                    status="failed",
                    error_code="VALIDATION_FAILED",
                    error_message=str(exc),
                )
        elif result.video_path:
            path = Path(result.video_path)
            if path.is_file() and path.stat().st_size > 0:
                output_sha = _sha256(path)

        with self.connection:
            cur = self.connection.execute(
                """
                UPDATE video_factory_scene_operation
                SET status = ?,
                    provider_operation_id = COALESCE(?, video_factory_scene_operation.provider_operation_id),
                    output_path = COALESCE(?, video_factory_scene_operation.output_path),
                    output_sha256 = CASE WHEN ? != '' THEN ? ELSE video_factory_scene_operation.output_sha256 END,
                    error_code = ?,
                    error_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE operation_id = ?
                  AND status NOT IN ('completed', 'failed')
                """,
                (
                    result.status,
                    result.provider_operation_id,
                    result.video_path,
                    output_sha,
                    output_sha,
                    result.error_code,
                    result.error_message,
                    request.request_id,
                ),
            )
            if cur.rowcount == 0 and not existing:
                self.connection.execute(
                    """
                    INSERT INTO video_factory_scene_operation (
                        operation_id, owner_user_id, project_id, scene_id,
                        request_digest, provider_operation_id, status, output_path,
                        output_sha256, error_code, error_message, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(operation_id) DO UPDATE SET
                        status = CASE WHEN video_factory_scene_operation.status IN ('completed', 'failed') THEN video_factory_scene_operation.status ELSE excluded.status END,
                        provider_operation_id = COALESCE(video_factory_scene_operation.provider_operation_id, excluded.provider_operation_id),
                        output_path = COALESCE(video_factory_scene_operation.output_path, excluded.output_path),
                        output_sha256 = CASE WHEN excluded.output_sha256 != '' THEN excluded.output_sha256 ELSE video_factory_scene_operation.output_sha256 END,
                        error_code = excluded.error_code,
                        error_message = excluded.error_message,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE video_factory_scene_operation.status NOT IN ('completed', 'failed')
                    """,
                    (
                        request.request_id,
                        request.owner_user_id,
                        request.project_id,
                        request.scene_id,
                        digest,
                        result.provider_operation_id,
                        result.status,
                        result.video_path,
                        output_sha,
                        result.error_code,
                        result.error_message,
                    ),
                )

    def reconcile_submitting_operation(
        self,
        operation_id: str,
        *,
        action: Literal["bind", "fail"],
        provider_operation_id: str | None = None,
        error_message: str = "",
    ) -> dict[str, Any]:
        """Operator reconciliation for an operation stuck in 'submitting' after crash."""
        existing = self.get(operation_id)
        if not existing:
            raise ValueError(f"Operation {operation_id} not found")
        if existing["status"] != "submitting":
            raise ValueError(f"Operation {operation_id} is in status {existing['status']}, not 'submitting'")

        with self.connection:
            if action == "bind":
                if not provider_operation_id or not provider_operation_id.strip():
                    raise ValueError("provider_operation_id is required to bind a submitting operation")
                self.connection.execute(
                    """
                    UPDATE video_factory_scene_operation
                    SET status = 'running',
                        provider_operation_id = ?,
                        error_code = '',
                        error_message = '',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE operation_id = ? AND status = 'submitting'
                    """,
                    (provider_operation_id.strip(), operation_id),
                )
            elif action == "fail":
                self.connection.execute(
                    """
                    UPDATE video_factory_scene_operation
                    SET status = 'failed',
                        error_code = 'OPERATOR_RECONCILED_FAILED',
                        error_message = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE operation_id = ? AND status = 'submitting'
                    """,
                    (error_message or "Submission reconciled as failed by operator", operation_id),
                )
            else:
                raise ValueError(f"Unknown reconciliation action: {action}")
        return dict(self.get(operation_id))


class SceneRenderRuntime:
    def __init__(
        self, *, store: SceneRenderOperationStore, provider: VideoGenerationPort
    ) -> None:
        self.store = store
        self.provider = provider

    def run(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        existing = self.store.get(request.request_id)
        if existing:
            if existing["request_digest"] != stable_scene_request_digest(request):
                raise ValueError("video scene operation idempotency conflict")
            if existing["status"] == "completed":
                output = Path(existing["output_path"] or "")
                if (
                    output.is_file()
                    and existing["output_sha256"]
                    and _sha256(output) == existing["output_sha256"]
                ):
                    return VideoGenerationResult(
                        request_id=request.request_id,
                        status="completed",
                        provider_operation_id=existing["provider_operation_id"],
                        video_path=str(output),
                    )
                raise ValueError("completed video scene artifact is missing or changed")
            provider_operation_id = existing["provider_operation_id"]
            if provider_operation_id:
                result = self.provider.get_status(provider_operation_id)
                result = replace(result, request_id=request.request_id)
                self.store.save_result(request, result)
                return result
            if existing["status"] == "submitting":
                # Check if provider supports idempotency reconciliation before refusing
                for lookup_fn in ("lookup_by_request_id", "get_by_request_id", "find_by_request_id"):
                    if hasattr(self.provider, lookup_fn):
                        try:
                            reconciled = getattr(self.provider, lookup_fn)(request.request_id)
                            if reconciled and reconciled.provider_operation_id:
                                reconciled = replace(reconciled, request_id=request.request_id)
                                self.store.save_result(request, reconciled)
                                return reconciled
                        except Exception:
                            pass
                return VideoGenerationResult(
                    request_id=request.request_id,
                    status="failed",
                    error_code="RECONCILIATION_REQUIRED",
                    error_message=(
                        "scene submission checkpoint has no provider operation id; "
                        "refusing a duplicate paid submission"
                    ),
                )
            if existing["status"] == "planned":
                transitioned = self.store.mark_submitting(request)
                if not transitioned:
                    # Reread if race occurred
                    existing = self.store.get(request.request_id)
                    if existing and existing["status"] != "planned":
                        return self.run(request)
        else:
            # Ensure planned first before submitting
            self.store.mark_planned(request)
            self.store.mark_submitting(request)

        result = self.provider.submit(request)
        result = replace(result, request_id=request.request_id)
        self.store.save_result(request, result)
        return result
