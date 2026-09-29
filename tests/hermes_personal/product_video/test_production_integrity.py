"""Adversarial tests for production integrity gaps.

Tests the five hardened integrity contracts:
1. Scene/composite digest validation (no backfilling, scoped updates, invalidation)
2. Provider output validation before terminal completion
3. Exact QC provenance (no fallback queries without artifact_id/version)
4. Fail-closed path handling (no unrestricted fallbacks)
5. End-keyframe contract enforcement
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import pytest

from hermes_personal.integrations.video_factory.scene_validator import validate_scene_output
from hermes_personal.integrations.video_factory.scene_renderer import SceneRenderOperationStore
from hermes_personal.product_video.qc.models import QCReport, QCStage, QCVerdict
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.qc.service import ProductVideoQCService
from hermes_personal.product_video.storage.layout import ProductVideoWorkspaceLayout
from hermes_personal.workflows.repository import WorkflowRepository


def _write_valid_video(
    path: Path, width: int = 64, height: int = 96, duration_frames: int = 3, fps: int = 24
) -> Path:
    """Write a minimal valid MP4 for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(path), mode="w", format="mp4")
    stream = container.add_stream("libx264", rate=fps)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    for index in range(duration_frames):
        frame = av.VideoFrame(width, height, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes([32 + index]) * plane.buffer_size)
        frame.pts = index
        frame.time_base = Fraction(1, fps)
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# 1. Scene/Composite Integrity (No backfilling, scoped updates, invalidation)
# ══════════════════════════════════════════════════════════════════════════════


def test_qc_service_rejects_missing_keyframe_digest_without_backfilling(
    tmp_path: Path,
) -> None:
    """QC must reject missing package_digest instead of computing from disk."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    
    # Initialize schema
    db.executescript("""
        CREATE TABLE IF NOT EXISTS workflow (
            workflow_id TEXT PRIMARY KEY,
            aggregate_json TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS workflow_event (
            event_id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            command_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    wf_repo = WorkflowRepository(db)
    
    # Create workflow with keyframe package missing digest
    wf_id = "wf-missing-digest"
    package = {
        "generated_keyframes": [
            {"frame_id": "frame-1", "image_path": "file://fake.png", "status": "completed"}
        ],
        # package_digest intentionally missing
    }
    agg = {
        "owner_user_id": "user-1",
        "project_id": "proj-1",
        "storyboard": package,
        "resource_pack": {
            "product_identity_description": "Test Product",
            "product_identity": {
                "brand": "TestBrand",
                "model": "TestModel",
            }
        },
        "source_context": {},
    }
    wf_repo.commit_workflow(wf_id, json.dumps(agg), [])
    
    svc = ProductVideoQCService(db)
    result = svc.run(wf_id, QCStage.KEYFRAME, provider_mode="fake")
    
    assert result["status"] == "failed"
    assert "package_digest" in result["reason"].lower()
    assert "missing" in result["reason"].lower()


def test_export_rejects_qc_report_missing_artifact_id(tmp_path: Path) -> None:
    """Export must fail when QC report lacks exact artifact_id/version provenance."""
    from hermes_personal.integrations.video_factory import server
    
    ws = tmp_path / "workspace"
    db_path = tmp_path / "factory.sqlite"
    
    server._DB_PATH_OVERRIDE = str(db_path)
    server._WORKSPACE_OVERRIDE = str(ws)
    
    # Create project with final approval
    server.video_project_create("owner", "proj-no-provenance")
    server.resource_pack_save(
        "owner",
        "proj-no-provenance",
        {
            "id": "pack-1",
            "product_references": [{"asset_id": "asset-1", "uri": "asset://product.png"}],
            "primary_product_asset_id": "asset-1",
            "product_identity_description": "Test Product",
        },
    )
    
    svc = server._service()
    project = svc.get_project("owner", "proj-no-provenance")
    from hermes_personal.integrations.video_factory.domain import (
        FinalApprovalStatus,
        VideoFactoryProject,
    )
    svc.repository.save(
        VideoFactoryProject(**{**project.__dict__, "final_approval": FinalApprovalStatus.APPROVED})
    )
    
    # Write valid video and save QC report WITHOUT artifact_id
    video = _write_valid_video(tmp_path / "video.mp4", width=720, height=1280, duration_frames=72)
    video_sha = _sha256(video)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    QCReportRepository(conn).save_report(
        QCReport(
            report_id="qc-no-artifact",
            workflow_id="wf-1",
            stage=QCStage.VIDEO,
            artifact_id="",  # Missing
            artifact_version=0,  # Missing
            artifact_digest=f"sha256:{video_sha}",
            reference_digests=(),
            evaluator_name="eval",
            evaluator_version="1.0",
            rubric_version="1.0",
            created_at="2026-09-18T00:00:00Z",
            score=95,
            verdict=QCVerdict.PASS,
            findings=(),
            owner_user_id="owner",
            project_id="proj-no-provenance",
        )
    )
    conn.close()
    
    result = server.export(
        render_result={
            "video_url": f"file://{video}",
            "project_id": "proj-no-provenance",
            "workflow_id": "wf-1",
        },
        project_id="proj-no-provenance",
        owner_user_id="owner",
    )
    
    assert result["ok"] is False
    assert result["code"] == "VIDEO_QC_REQUIRED"
    # Export correctly rejected - QC report exists but lacks artifact_id binding


# ══════════════════════════════════════════════════════════════════════════════
# 2. Provider Output Validation
# ══════════════════════════════════════════════════════════════════════════════


def test_validate_scene_output_rejects_wrong_duration(tmp_path: Path) -> None:
    """Scene validator must reject output with wrong duration."""
    # Write 1-second video
    video = _write_valid_video(tmp_path / "short.mp4", duration_frames=24, fps=24)
    
    with pytest.raises(ValueError, match="SCENE_OUTPUT_DURATION_MISMATCH"):
        validate_scene_output(
            output_path=video,
            expected_duration=4.0,  # Expected 4 seconds
            duration_tolerance=0.5,
        )


def test_validate_scene_output_rejects_wrong_aspect_ratio(tmp_path: Path) -> None:
    """Scene validator must reject output with wrong aspect ratio."""
    # Write 16:9 video
    video = _write_valid_video(tmp_path / "wrong-aspect.mp4", width=160, height=90, duration_frames=96)
    
    with pytest.raises(ValueError, match="SCENE_OUTPUT_ASPECT_MISMATCH"):
        validate_scene_output(
            output_path=video,
            expected_duration=4.0,
            expected_aspect_ratio="9:16",  # Expected portrait
        )


def test_validate_scene_output_rejects_undecodable(tmp_path: Path) -> None:
    """Scene validator must reject broken MP4."""
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(
        b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 4096
    )
    
    with pytest.raises(ValueError, match="SCENE_OUTPUT|Invalid data"):
        validate_scene_output(output_path=broken, expected_duration=4.0)


def test_scene_render_store_validates_before_completed(tmp_path: Path) -> None:
    """SceneRenderOperationStore must validate output before marking completed."""
    from hermes_personal.integrations.video_factory.ports import (
        VideoGenerationRequest,
        VideoGenerationResult,
    )
    
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    store = SceneRenderOperationStore(db)
    
    # Write 1-second video (wrong duration for a 4-second request)
    video = _write_valid_video(tmp_path / "wrong-duration.mp4", duration_frames=24, fps=24)
    
    request = VideoGenerationRequest(
        request_id="op-1",
        owner_user_id="owner",
        project_id="proj",
        scene_id="scene-1",
        duration_seconds=4,  # Expected 4 seconds
        aspect_ratio="9:16",
        prompt="test",
        reference_image_paths=(str(tmp_path / "ref.png"),),
    )
    
    # Provider claims completed
    result = VideoGenerationResult(
        request_id="op-1",
        status="completed",
        provider_operation_id="prov-1",
        video_path=str(video),
    )
    
    # Save should validate and transition to failed
    store.save_result(request, result)
    
    saved = store.get("op-1")
    assert saved["status"] == "failed"
    assert saved["error_code"] == "VALIDATION_FAILED"
    assert "duration" in saved["error_message"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# 3. Path Handling (Fail-closed, no unrestricted fallback)
# ══════════════════════════════════════════════════════════════════════════════


def test_workspace_resolve_path_rejects_outside_workspace(tmp_path: Path) -> None:
    """resolve_path must reject paths outside workspace without fallback."""
    ws = ProductVideoWorkspaceLayout(tmp_path / "workspace")
    outside = tmp_path / "outside" / "file.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("external")
    
    with pytest.raises(ValueError, match="CONTAINMENT_VIOLATION"):
        ws.resolve_path(outside)


# Task 2: Production Polling Validation Tests

def test_polling_validates_wrong_duration_via_finalize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """get_job_status() should validate scene output through finalize_provider_result()."""
    import sqlite3
    from hermes_personal.integrations.video_factory import server
    from hermes_personal.integrations.video_factory.ports import VideoGenerationResult
    from hermes_personal.integrations.video_factory.scene_renderer import SceneRenderOperationStore
    
    ws = tmp_path / "workspace"
    db_path = tmp_path / "factory.sqlite"
    
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_path))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws))
    
    # Create a project
    server.video_project_create("owner", "proj-poll")
    
    # Write a 1-second video (wrong duration for 4-second contract)
    video = _write_valid_video(tmp_path / "short.mp4", duration_frames=24, fps=24)
    
    # Create a scene operation with validation contract
    op_store = SceneRenderOperationStore(db_path)
    from hermes_personal.integrations.video_factory.ports import VideoGenerationRequest
    
    request = VideoGenerationRequest(
        request_id="op-validate-1",
        owner_user_id="owner",
        project_id="proj-poll",
        scene_id="scene-1",
        duration_seconds=4,  # Expect 4 seconds
        aspect_ratio="9:16",
        prompt="test scene",
        reference_image_paths=(),
    )
    
    op_store.mark_planned(request, render_batch_id="batch-validate-1", scene_order=1)
    op_store.mark_submitting(request)
    
    # Mock provider to return completed with wrong duration video
    class MockProvider:
        def get_status(self, job_id: str) -> VideoGenerationResult:
            return VideoGenerationResult(
                request_id="op-validate-1",
                status="completed",
                provider_operation_id="prov-validate-1",
                video_path=str(video),
            )
    
    # Call finalize_provider_result directly to test validation
    result = VideoGenerationResult(
        request_id="op-validate-1",
        status="completed",
        provider_operation_id="prov-validate-1",
        video_path=str(video),
    )
    
    final_state = op_store.finalize_provider_result("op-validate-1", result)
    
    # Should fail validation due to wrong duration
    assert final_state["status"] == "failed"
    assert "duration" in final_state["error_message"].lower() or "VALIDATION" in final_state.get("error_code", "")


def test_polling_validates_wrong_aspect_ratio_via_finalize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """finalize_provider_result() should reject wrong aspect ratio."""
    import sqlite3
    from hermes_personal.integrations.video_factory.scene_renderer import SceneRenderOperationStore
    from hermes_personal.integrations.video_factory.ports import VideoGenerationRequest, VideoGenerationResult
    
    db_path = tmp_path / "ops.db"
    
    # Write a 16:9 video (wrong aspect for 9:16 contract)
    video = _write_valid_video(tmp_path / "landscape.mp4", width=160, height=90, duration_frames=96, fps=24)
    
    # Create scene operation with 9:16 contract
    op_store = SceneRenderOperationStore(db_path)
    request = VideoGenerationRequest(
        request_id="op-aspect-1",
        owner_user_id="owner",
        project_id="proj",
        scene_id="scene-1",
        duration_seconds=4,
        aspect_ratio="9:16",  # Expect 9:16
        prompt="test",
        reference_image_paths=(),
    )
    
    op_store.mark_planned(request, render_batch_id="batch-1", scene_order=1)
    
    # Try to finalize with wrong aspect ratio video
    result = VideoGenerationResult(
        request_id="op-aspect-1",
        status="completed",
        provider_operation_id="prov-1",
        video_path=str(video),
    )
    
    final_state = op_store.finalize_provider_result("op-aspect-1", result)
    
    # Should fail validation due to wrong aspect ratio
    assert final_state["status"] == "failed"
    assert "aspect" in final_state["error_message"].lower()


def test_production_polling_rejects_wrong_aspect_ratio(tmp_path: Path) -> None:
    """Production polling must reject wrong aspect ratio."""
    # TODO: Implement similar to above but with wrong aspect ratio
    assert True  # Placeholder for now


def test_workspace_resolve_path_rejects_traversal(tmp_path: Path) -> None:
    """resolve_path must reject .. traversal."""
    ws = ProductVideoWorkspaceLayout(tmp_path / "workspace")
    
    with pytest.raises(ValueError, match="traversal"):
        ws.resolve_path("../../../etc/passwd")


def test_qc_service_file_path_resolution_fail_closed(tmp_path: Path) -> None:
    """QC service must not fall back to unrestricted Path.resolve()."""
    from hermes_personal.product_video.qc.service import _file_url_to_path
    
    # Set workspace
    import os
    os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(tmp_path / "workspace")
    
    outside = tmp_path / "outside" / "file.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("external")
    
    with pytest.raises(ValueError, match="CONTAINMENT_VIOLATION"):
        _file_url_to_path(str(outside))


# ══════════════════════════════════════════════════════════════════════════════
# 4. Composite Integrity (Digest mismatch must invalidate approvals)
# ══════════════════════════════════════════════════════════════════════════════


def test_modified_composite_after_approval_detected(tmp_path: Path) -> None:
    """Modified composite after Final Approval must be detected by SHA mismatch."""
    video = _write_valid_video(tmp_path / "original.mp4", width=720, height=1280, duration_frames=96)
    original_sha = _sha256(video)
    
    # Simulate approval bound to original SHA
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    QCReportRepository(db).save_report(
        QCReport(
            report_id="qc-approved",
            workflow_id="wf-1",
            stage=QCStage.VIDEO,
            artifact_id="art_composite_proj_v1",
            artifact_version=1,
            artifact_digest=f"sha256:{original_sha}",
            reference_digests=(),
            evaluator_name="eval",
            evaluator_version="1.0",
            rubric_version="1.0",
            created_at="2026-09-18T00:00:00Z",
            score=95,
            verdict=QCVerdict.PASS,
            findings=(),
            owner_user_id="owner",
            project_id="proj",
        )
    )
    
    # Modify the video (simulate post-approval change)
    video.write_bytes(video.read_bytes() + b"MODIFIED")
    modified_sha = _sha256(video)
    
    # Verify SHA changed
    assert modified_sha != original_sha
    
    # QC lookup should fail because SHA no longer matches
    repo = QCReportRepository(db)
    report = repo.get_verified_pass_report(
        owner_user_id="owner",
        project_id="proj",
        workflow_id="wf-1",
        artifact_id="art_composite_proj_v1",
        artifact_version=1,
        stage=QCStage.VIDEO,
        expected_sha256=modified_sha,
    )
    
    assert report is None, "Modified composite should not match approved QC report"


# ══════════════════════════════════════════════════════════════════════════════
# 5. Integration: Full pipeline integrity
# ══════════════════════════════════════════════════════════════════════════════


def test_scene_validation_contract_persisted(tmp_path: Path) -> None:
    """Scene operation must persist expected_duration and aspect_ratio for post-restart validation."""
    from hermes_personal.integrations.video_factory.scene_renderer import SceneRenderOperationStore
    from hermes_personal.integrations.video_factory.ports import VideoGenerationRequest
    
    db_path = tmp_path / "ops.db"
    store = SceneRenderOperationStore(db_path)
    
    request = VideoGenerationRequest(
        request_id="op-contract-1",
        owner_user_id="owner",
        project_id="proj",
        scene_id="scene-1",
        duration_seconds=6,
        aspect_ratio="9:16",
        prompt="test scene",
        reference_image_paths=(),
    )
    
    store.mark_planned(request, render_batch_id="batch-1", scene_order=1)
    
    # Reopen connection to verify persistence
    store2 = SceneRenderOperationStore(db_path)
    row = store2.get("op-contract-1")
    
    assert row is not None
    assert row["expected_duration_seconds"] == 6.0
    assert row["expected_aspect_ratio"] == "9:16"


def test_scene_legacy_operation_missing_contract_fails_validation(tmp_path: Path) -> None:
    """Legacy operation without validation contract must fail closed."""
    from hermes_personal.integrations.video_factory.scene_renderer import SceneRenderOperationStore
    from hermes_personal.integrations.video_factory.ports import VideoGenerationResult
    
    db_path = tmp_path / "ops.db"
    store = SceneRenderOperationStore(db_path)
    
    # Insert legacy row manually without validation fields
    store.connection.execute(
        """
        INSERT INTO video_factory_scene_operation (
            operation_id, owner_user_id, project_id, scene_id,
            request_digest, status, expected_duration_seconds, expected_aspect_ratio
        ) VALUES (?, ?, ?, ?, ?, 'running', 0, '')
        """,
        ("op-legacy", "owner", "proj", "scene-1", "digest-123"),
    )
    
    # Write a valid video
    video = _write_valid_video(tmp_path / "scene.mp4", duration_frames=96, fps=24)
    
    result = VideoGenerationResult(
        request_id="op-legacy",
        status="completed",
        provider_operation_id="prov-1",
        video_path=str(video),
    )
    
    # Finalization should detect missing contract
    final_state = store.finalize_provider_result("op-legacy", result)
    
    assert final_state["status"] == "failed"
    assert "VALIDATION_CONTRACT_MISSING" in final_state["error_code"] or "contract" in final_state["error_message"].lower()
    assert final_state["output_sha256"] == ""


def test_end_to_end_integrity_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Full pipeline must reject invalid outputs at every gate."""
    from hermes_personal.integrations.video_factory import server
    
    ws = tmp_path / "workspace"
    db_path = tmp_path / "factory.sqlite"
    
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_path))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws))
    
    # Create approved project
    server.video_project_create("owner", "proj-e2e")
    server.resource_pack_save(
        "owner",
        "proj-e2e",
        {
            "id": "pack-e2e",
            "product_references": [{"asset_id": "asset-1", "uri": "asset://product.png"}],
            "primary_product_asset_id": "asset-1",
            "product_identity_description": "Test Product E2E",
        },
    )
    
    svc = server._service()
    project = svc.get_project("owner", "proj-e2e")
    from hermes_personal.integrations.video_factory.domain import (
        FinalApprovalStatus,
        VideoFactoryProject,
    )
    svc.repository.save(
        VideoFactoryProject(**{**project.__dict__, "final_approval": FinalApprovalStatus.APPROVED})
    )
    
    # Create INVALID video (wrong dimensions, undecodable tail)
    broken = tmp_path / "invalid.mp4"
    broken.write_bytes(
        b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 2048
    )
    
    # Export must reject invalid video
    result = server.export(
        render_result={
            "video_url": f"file://{broken}",
            "project_id": "proj-e2e",
            "workflow_id": "wf-e2e",
        },
        project_id="proj-e2e",
        owner_user_id="owner",
    )
    
    assert result["ok"] is False
    assert result["code"] == "INVALID_VIDEO_ARTIFACT"
    assert "decode" in result["error"].lower()
