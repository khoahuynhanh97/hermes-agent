from __future__ import annotations

import pytest

from mcp_servers.video import server


def test_video_create_job_and_get_status_are_owner_scoped(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    asset = workspace / "source.mp4"
    asset.write_bytes(b"test media")
    monkeypatch.setenv("HERMES_VIDEO_WORKSPACE", str(workspace))
    monkeypatch.setenv("HERMES_VIDEO_DB_PATH", str(tmp_path / "video.sqlite"))

    created = server.video_create_job(
        "owner-1",
        "cut",
        str(asset),
        output_name="cut.mp4",
        start_seconds=0,
        end_seconds=5,
    )
    job = created["job"]
    assert created["execution_mode"] == "durable_job"
    assert job["status"] == "queued"
    assert job["owner_user_id"] == "owner-1"
    assert server.video_get_job("owner-1", job["job_id"])["job"]["status"] == "queued"

    with pytest.raises(ValueError, match="OWNER_MISMATCH"):
        server.video_get_job("owner-2", job["job_id"])


def test_video_paths_and_operations_are_bounded(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    asset = workspace / "source.mp4"
    asset.write_bytes(b"test media")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    monkeypatch.setenv("HERMES_VIDEO_WORKSPACE", str(workspace))
    monkeypatch.setenv("HERMES_VIDEO_DB_PATH", str(tmp_path / "video.sqlite"))

    with pytest.raises(ValueError, match="UNAUTHORIZED_PATH"):
        server.video_create_job("owner-1", "cut", str(outside))
    with pytest.raises(ValueError, match="unsupported output format"):
        server.video_create_job("owner-1", "render", str(asset), output_format="avi")
    with pytest.raises(ValueError, match="operation"):
        server.video_create_job("owner-1", "ffmpeg", str(asset))


def test_video_analyze_uses_existing_offline_capability(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    asset = workspace / "source.mp4"
    asset.write_bytes(b"test media")
    monkeypatch.setenv("HERMES_VIDEO_WORKSPACE", str(workspace))
    monkeypatch.setattr(server, "analyze_video", lambda *args, **kwargs: "offline observations")

    result = server.video_analyze("owner-1", str(asset))
    assert result["mode"] == "offline_inspection"
    assert result["analysis"] == "offline observations"
