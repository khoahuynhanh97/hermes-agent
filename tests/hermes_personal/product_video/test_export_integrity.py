from __future__ import annotations

from pathlib import Path
from fractions import Fraction
import json

import av
import pytest

from hermes_personal.integrations.video_factory.composer import (
    InvalidVideoArtifact,
    VideoExpectation,
    VideoProbe,
    build_video_metadata,
    probe_video,
    validate_export,
)
from hermes_personal.integrations.video_factory import server
from hermes_personal.integrations.video_factory.domain import (
    FinalApprovalStatus,
    VideoFactoryProject,
)


def _write_valid_video(path: Path) -> Path:
    container = av.open(str(path), mode="w", format="mp4")
    stream = container.add_stream("libx264", rate=24)
    stream.width = 64
    stream.height = 96
    stream.pix_fmt = "yuv420p"
    for index in range(3):
        frame = av.VideoFrame(64, 96, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes([32 + index]) * plane.buffer_size)
        frame.pts = index
        frame.time_base = Fraction(1, 24)
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return path


def test_probe_rejects_ftyp_followed_by_zero_bytes(tmp_path: Path) -> None:
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(
        b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
        + b"\x00" * 4096
    )

    with pytest.raises(InvalidVideoArtifact, match="decode"):
        probe_video(broken, decode_all=True)


def test_export_rejects_undecodable_video_instead_of_fabricating_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "factory.sqlite"))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(tmp_path / "workspace"))
    server.video_project_create("owner", "proj-invalid-video")
    server.resource_pack_save(
        "owner",
        "proj-invalid-video",
        {
            "id": "pack-invalid-video",
            "product_references": [{"asset_id": "asset-1", "uri": "asset://product.png"}],
            "primary_product_asset_id": "asset-1",
            "product_identity_description": "Baseus Bowie WM02",
        },
    )
    service = server._service()
    project = service.get_project("owner", "proj-invalid-video")
    service.repository.save(
        VideoFactoryProject(
            **{
                **project.__dict__,
                "final_approval": FinalApprovalStatus.APPROVED,
            }
        )
    )
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(
        b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
        + b"\x00" * 4096
    )

    result = server.export(
        render_result={"video_url": f"file://{broken}", "project_id": "proj-invalid-video"},
        project_id="proj-invalid-video",
        owner_user_id="owner",
    )

    assert result["ok"] is False
    assert result["code"] == "INVALID_VIDEO_ARTIFACT"
    assert not list((tmp_path / "workspace" / "exports").glob("*.mp4"))


def test_server_export_uses_canonical_immutable_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "factory.sqlite"))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(tmp_path / "workspace"))
    server.video_project_create("owner", "proj-canonical")
    server.resource_pack_save(
        "owner",
        "proj-canonical",
        {
            "id": "pack-canonical",
            "product_references": [{"asset_id": "asset-1", "uri": "asset://product.png"}],
            "primary_product_asset_id": "asset-1",
            "product_identity_description": "Baseus Bowie WM02",
        },
    )
    service = server._service()
    project = service.get_project("owner", "proj-canonical")
    service.repository.save(
        VideoFactoryProject(
            **{
                **project.__dict__,
                "final_approval": FinalApprovalStatus.APPROVED,
            }
        )
    )
    video = _write_valid_video(tmp_path / "final-source.mp4")
    from hermes_personal.integrations.video_factory.composer import compute_file_sha256
    from hermes_personal.product_video.qc.repository import QCReportRepository
    from hermes_personal.product_video.qc.models import QCReport, QCStage, QCVerdict
    import sqlite3
    qc_conn = sqlite3.connect(tmp_path / "factory.sqlite")
    QCReportRepository(qc_conn).save_report(
        QCReport(
            report_id="qc-video-1",
            workflow_id="wf-canonical",
            stage=QCStage.VIDEO,
            artifact_id="art-canonical",
            artifact_version=1,
            artifact_digest=f"sha256:{compute_file_sha256(video)}",
            reference_digests=(),
            evaluator_name="evaluator",
            evaluator_version="1.0",
            rubric_version="1.0",
            created_at="2026-09-17T00:00:00Z",
            score=95,
            verdict=QCVerdict.PASS,
            findings=(),
            owner_user_id="owner",
            project_id="proj-canonical",
        )
    )
    qc_conn.close()

    # Patch the delivery-spec expectation so the 64×96 test fixture passes validation.
    # Production code enforces 1080×1920; this override is test-scoped only.
    monkeypatch.setattr(
        server,
        "_EXPORT_VIDEO_EXPECTATION",
        VideoExpectation(width=64, height=96, duration_seconds=probe_video(video).duration_seconds, codec="h264", fps=24.0, min_frames=1, max_duration_delta=0.5),
    )

    result = server.export(
        render_result={
            "video_url": f"file://{video}",
            "project_id": "proj-canonical",
            "workflow_id": "wf-canonical",
            "version": 1,
            "artifact_id": "art-canonical",
            "video_qc_report_id": "qc-video-1",
            "provider_operations": [{"scene_id": "scene-1", "operation_id": "vertex-op-1"}],
            "spend": {"total_usd": 8.5},
        },
        export_params={"version": "v7", "artifact_digests": {"storyboard": "sha256:abc"}},
        project_id="proj-canonical",
        owner_user_id="owner",
    )

    expected = tmp_path / "workspace" / "exports" / "export_proj-canonical_v7"
    assert result["ok"] is True
    assert Path(result["file_path"]) == expected / "final.mp4"
    assert Path(result["caption_path"]) == expected / "caption.txt"
    assert Path(result["metadata_path"]) == expected / "metadata.json"
    metadata = json.loads((expected / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["video"]["frame_count"] == 3
    assert metadata["provenance"]["provider_operations"][0]["operation_id"] == "vertex-op-1"
    assert metadata["provenance"]["artifact_digests"]["storyboard"] == "sha256:abc"
    assert metadata["provenance"]["spend"]["total_usd"] == 8.5


def test_probe_rejects_truncated_mp4(tmp_path: Path) -> None:
    valid = _write_valid_video(tmp_path / "valid.mp4")
    content = valid.read_bytes()
    truncated = tmp_path / "truncated.mp4"
    truncated.write_bytes(content[: len(content) // 3])

    with pytest.raises(InvalidVideoArtifact, match="decode"):
        probe_video(truncated, decode_all=True)


def test_validate_export_success_and_failure(tmp_path: Path) -> None:
    valid = _write_valid_video(tmp_path / "valid.mp4")
    probe = validate_export(
        valid,
        expected=VideoExpectation(
            width=64,
            height=96,
            duration_seconds=0.125,
            codec="h264",
            fps=24.0,
            min_frames=3,
            max_duration_delta=0.5,
        ),
    )
    assert isinstance(probe, VideoProbe)
    assert probe.width == 64
    assert probe.height == 96

    # Resolution mismatch
    with pytest.raises(InvalidVideoArtifact, match="resolution mismatch"):
        validate_export(
            valid,
            expected=VideoExpectation(
                width=720,
                height=1280,
                duration_seconds=0.125,
            ),
        )

    # Duration mismatch
    with pytest.raises(InvalidVideoArtifact, match="duration mismatch"):
        validate_export(
            valid,
            expected=VideoExpectation(
                width=64,
                height=96,
                duration_seconds=16.0,
                max_duration_delta=0.5,
            ),
        )


def test_export_metadata_is_derived_from_probe(tmp_path: Path) -> None:
    valid = _write_valid_video(tmp_path / "valid.mp4")
    probe = probe_video(valid, decode_all=True)
    metadata = build_video_metadata(probe)
    assert metadata["sha256"] == probe.sha256
    assert metadata["duration_seconds"] == probe.duration_seconds
    assert metadata["resolution"] == f"{probe.width}x{probe.height}"
    assert metadata["fps"] == probe.fps
    assert metadata["frame_count"] == probe.frame_count
    assert metadata["codec"] == probe.codec

