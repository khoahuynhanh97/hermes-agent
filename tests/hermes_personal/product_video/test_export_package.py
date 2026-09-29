from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import av
import pytest

from hermes_personal.integrations.video_factory.export_package import (
    ExportPackageConflict,
    build_export_package,
)


def _write_video(path: Path, *, frames: int = 3, color: int = 32) -> Path:
    container = av.open(str(path), mode="w", format="mp4")
    stream = container.add_stream("libx264", rate=24)
    stream.width = 64
    stream.height = 96
    stream.pix_fmt = "yuv420p"
    for index in range(frames):
        frame = av.VideoFrame(64, 96, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes([(color + index) % 256]) * plane.buffer_size)
        frame.pts = index
        frame.time_base = Fraction(1, 24)
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return path


def test_build_export_package_writes_immutable_versioned_files_and_truthful_metadata(
    tmp_path: Path,
) -> None:
    source = _write_video(tmp_path / "source.mp4")

    package = build_export_package(
        source_video=source,
        exports_root=tmp_path / "exports",
        project_id="proj-123",
        version="v1",
        product_identity="Baseus Bowie WM02",
        verified_claims=["Bluetooth 5.3", "Minh Gear chính hãng ưu đãi"],
        cta="Xem thông tin sản phẩm; đặt hàng tại shop",
        provenance={
            "approvals": {"final_video": "approval-final"},
            "artifact_digests": {"storyboard": "sha256:storyboard"},
            "provider_operations": [{"scene_id": "scene-1", "operation_id": "op-1"}],
            "qc": {"video": {"status": "PASS", "report_id": "qc-video-1"}},
            "spend": {"total_usd": 8.25},
        },
    )

    assert package.directory == tmp_path / "exports" / "export_proj-123_v1"
    assert package.video_path.name == "final.mp4"
    assert package.caption_path.name == "caption.txt"
    assert package.metadata_path.name == "metadata.json"
    assert package.video_path.read_bytes() == source.read_bytes()

    caption = package.caption_path.read_text(encoding="utf-8").lower()
    assert "baseus bowie wm02" in caption
    assert "bluetooth 5.3" in caption
    assert "minh gear" not in caption
    assert "chính hãng" not in caption
    assert "ưu đãi" not in caption
    assert "đặt hàng" not in caption
    assert "shop" not in caption
    assert "#review" not in caption

    metadata = json.loads(package.metadata_path.read_text(encoding="utf-8"))
    assert metadata["schema_version"] == "product-video-export-v2"
    assert metadata["video"]["width"] == 64
    assert metadata["video"]["height"] == 96
    assert metadata["video"]["frame_count"] == 3
    assert metadata["video"]["sha256"] == package.video_sha256
    assert Path(metadata["video"]["path"]) == package.video_path
    assert metadata["files"]["caption.txt"]["sha256"] == package.caption_sha256
    assert metadata["provenance"]["approvals"]["final_video"] == "approval-final"
    assert metadata["provenance"]["spend"]["total_usd"] == 8.25


def test_export_version_is_idempotent_but_never_overwritten(tmp_path: Path) -> None:
    source = _write_video(tmp_path / "source.mp4", color=20)
    kwargs = {
        "source_video": source,
        "exports_root": tmp_path / "exports",
        "project_id": "proj-123",
        "version": "v1",
        "product_identity": "Baseus Bowie WM02",
    }

    first = build_export_package(**kwargs)
    original = first.video_path.read_bytes()
    again = build_export_package(**kwargs)
    assert again.video_sha256 == first.video_sha256

    changed = _write_video(tmp_path / "changed.mp4", color=200)
    with pytest.raises(ExportPackageConflict, match="already exists"):
        build_export_package(**{**kwargs, "source_video": changed})

    assert first.video_path.read_bytes() == original


def test_changed_video_requires_a_new_export_version(tmp_path: Path) -> None:
    first_video = _write_video(tmp_path / "first.mp4", color=20)
    second_video = _write_video(tmp_path / "second.mp4", color=200)

    first = build_export_package(
        source_video=first_video,
        exports_root=tmp_path / "exports",
        project_id="proj-123",
        version="v1",
        product_identity="Baseus Bowie WM02",
    )
    second = build_export_package(
        source_video=second_video,
        exports_root=tmp_path / "exports",
        project_id="proj-123",
        version="v2",
        product_identity="Baseus Bowie WM02",
    )

    assert first.directory != second.directory
    assert first.video_sha256 != second.video_sha256
    assert first.video_path.is_file()
    assert second.video_path.is_file()


def test_invalid_video_creates_no_export_directory(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not an mp4")

    with pytest.raises(ValueError, match="decode"):
        build_export_package(
            source_video=invalid,
            exports_root=tmp_path / "exports",
            project_id="proj-123",
            version="v1",
            product_identity="Baseus Bowie WM02",
        )

    assert not (tmp_path / "exports" / "export_proj-123_v1").exists()
