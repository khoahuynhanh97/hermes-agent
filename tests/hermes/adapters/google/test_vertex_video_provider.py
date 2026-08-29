"""Offline contract tests for VertexVideoProvider."""
from __future__ import annotations

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock

SRC_ROOT = Path(__file__).resolve().parents[4] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pytest

from hermes.adapters.google.vertex_video_provider import VertexVideoProvider
from hermes.ports.video_generation import VideoGenerationRequest


def test_provider_initialization_performs_no_io_or_network():
    """Provider initialization must be lazy and startup safe."""
    provider = VertexVideoProvider(project_id="test-proj", location="us-central1")
    assert provider.model == "veo-3.1-generate-001"
    assert provider.location == "us-central1"


def test_missing_credentials_fails_closed_before_http(tmp_path):
    """Missing auth must return failed result without making network calls."""
    mock_post = MagicMock()
    provider = VertexVideoProvider(
        project_id="test-proj",
        credential_resolver=lambda: (None, None),
        post_fn=mock_post,
        output_dir=tmp_path,
    )
    req = VideoGenerationRequest(
        request_id="req-1",
        owner_user_id="user-1",
        project_id="proj-1",
        scene_id="scene-1",
        prompt="A cute puppy playing in grass",
        duration_seconds=4,
        aspect_ratio="9:16",
    )
    result = provider.submit(req)
    assert result.status == "failed"
    assert result.error_code == "AUTH_FAILED"
    assert "MISSING_CREDENTIALS" in result.error_message
    mock_post.assert_not_called()


def test_submit_validates_duration_and_aspect_ratio(tmp_path):
    """Invalid duration or aspect ratio must fail closed with INVALID_INPUT."""
    provider = VertexVideoProvider(
        project_id="test-proj",
        credential_resolver=lambda: ("token-123", "test-proj"),
        output_dir=tmp_path,
    )
    # Invalid duration (e.g. 5 seconds)
    req_bad_duration = VideoGenerationRequest(
        request_id="req-1",
        owner_user_id="user-1",
        project_id="proj-1",
        scene_id="scene-1",
        prompt="Test prompt",
        duration_seconds=5,
    )
    res1 = provider.submit(req_bad_duration)
    assert res1.status == "failed"
    assert res1.error_code == "INVALID_INPUT"
    assert "duration_seconds" in res1.error_message

    # Invalid aspect ratio
    req_bad_ar = VideoGenerationRequest(
        request_id="req-2",
        owner_user_id="user-1",
        project_id="proj-1",
        scene_id="scene-1",
        prompt="Test prompt",
        duration_seconds=4,
        aspect_ratio="4:3",
    )
    res2 = provider.submit(req_bad_ar)
    assert res2.status == "failed"
    assert res2.error_code == "INVALID_INPUT"
    assert "aspect_ratio" in res2.error_message


def test_submit_encodes_reference_image_and_returns_full_operation_name(tmp_path):
    """Valid request with reference image dispatches exact predictLongRunning payload."""
    img_file = tmp_path / "reference.jpg"
    raw_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIFdummyimage"
    img_file.write_bytes(raw_bytes)

    captured_url = None
    captured_json = None
    captured_headers = None

    def fake_post(url, headers=None, json=None, timeout=None):
        nonlocal captured_url, captured_json, captured_headers
        captured_url = url
        captured_json = json
        captured_headers = headers
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "name": "projects/test-proj/locations/us-central1/publishers/google/models/veo-3.1-generate-001/operations/op-uuid-12345"
        }
        return resp

    provider = VertexVideoProvider(
        project_id="test-proj",
        location="us-central1",
        model="veo-3.1-generate-001",
        credential_resolver=lambda: ("mock-token-xyz", "test-proj"),
        post_fn=fake_post,
        output_dir=tmp_path / "ws",
    )

    req = VideoGenerationRequest(
        request_id="req-sub-1",
        owner_user_id="user-1",
        project_id="proj-1",
        scene_id="scene-1",
        prompt="Camera pans across modern gadget",
        duration_seconds=6,
        aspect_ratio="16:9",
        reference_image_paths=(str(img_file),),
        provider_options={"resolution": "1080p", "seed": 42},
    )

    res = provider.submit(req)
    assert res.status == "submitted"
    assert res.provider_operation_id == "projects/test-proj/locations/us-central1/publishers/google/models/veo-3.1-generate-001/operations/op-uuid-12345"
    assert captured_url == "https://us-central1-aiplatform.googleapis.com/v1/projects/test-proj/locations/us-central1/publishers/google/models/veo-3.1-generate-001:predictLongRunning"
    assert captured_headers == {"Authorization": "Bearer mock-token-xyz"}

    instances = captured_json["instances"]
    assert len(instances) == 1
    assert instances[0]["prompt"] == "Camera pans across modern gadget"
    assert instances[0]["image"]["mimeType"] == "image/jpeg"
    assert instances[0]["image"]["bytesBase64Encoded"] == base64.b64encode(raw_bytes).decode("ascii")

    params = captured_json["parameters"]
    assert params["durationSeconds"] == 6
    assert params["aspectRatio"] == "16:9"
    assert params["resolution"] == "1080p"
    assert params["seed"] == 42


def test_get_status_running(tmp_path):
    """Polling fetchPredictOperation when not done returns running status."""
    def fake_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"done": False}
        return resp

    provider = VertexVideoProvider(
        project_id="test-proj",
        credential_resolver=lambda: ("token", "test-proj"),
        post_fn=fake_post,
        output_dir=tmp_path,
    )
    res = provider.get_status("projects/test-proj/locations/us-central1/operations/op-999")
    assert res.status == "running"
    assert res.provider_operation_id == "projects/test-proj/locations/us-central1/operations/op-999"
    assert res.video_path is None


def test_get_status_completed_decodes_inline_mp4_deterministically(tmp_path):
    """Completed operation decodes inline base64 MP4 and saves to workspace output_dir."""
    mp4_bytes = b"\x00\x00\x00\x18ftypmp42fakevideocontent"
    b64_mp4 = base64.b64encode(mp4_bytes).decode("ascii")

    def fake_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "done": True,
            "response": {
                "videos": [{"bytesBase64Encoded": b64_mp4}]
            },
        }
        return resp

    ws_dir = tmp_path / "factory_ws"
    provider = VertexVideoProvider(
        project_id="test-proj",
        credential_resolver=lambda: ("token", "test-proj"),
        post_fn=fake_post,
        output_dir=ws_dir,
    )
    op_id = "projects/test-proj/locations/us-central1/publishers/google/models/veo/operations/op-uuid-8888"
    res = provider.get_status(op_id)
    assert res.status == "completed"
    assert res.video_path is not None

    saved_file = Path(res.video_path)
    assert saved_file.is_file()
    assert saved_file.read_bytes() == mp4_bytes
    assert saved_file.parent.resolve() == ws_dir.resolve()
    assert saved_file.name == "op-uuid-8888.mp4"


def test_get_status_provider_error(tmp_path):
    """Provider operation error returns failed status with provider error message."""
    def fake_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "done": True,
            "error": {"code": 3, "message": "Resource exhausted / quota exceeded"},
        }
        return resp

    provider = VertexVideoProvider(
        project_id="test-proj",
        credential_resolver=lambda: ("token", "test-proj"),
        post_fn=fake_post,
        output_dir=tmp_path,
    )
    res = provider.get_status("projects/test-proj/locations/us-central1/operations/op-failed")
    assert res.status == "failed"
    assert res.error_code == "PROVIDER_ERROR"
    assert "Resource exhausted" in res.error_message


def test_get_status_gcs_output_unsupported(tmp_path):
    """GCS URI without inline bytes returns structured GCS_OUTPUT_UNSUPPORTED."""
    def fake_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "done": True,
            "response": {"gcsUri": "gs://my-bucket/video.mp4"},
        }
        return resp

    provider = VertexVideoProvider(
        project_id="test-proj",
        credential_resolver=lambda: ("token", "test-proj"),
        post_fn=fake_post,
        output_dir=tmp_path,
    )
    res = provider.get_status("projects/test-proj/locations/us-central1/operations/op-gcs")
    assert res.status == "failed"
    assert res.error_code == "GCS_OUTPUT_UNSUPPORTED"
    assert "gs://my-bucket/video.mp4" in res.error_message
