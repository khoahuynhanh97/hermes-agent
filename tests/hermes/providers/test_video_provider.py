"""PVID1 tests: Vertex Veo video provider adapter + worker video_generate.

Vertex adapter tests mock HTTP (no paid calls). Worker tests use the
deterministic fake provider for sync completion and a scripted fake for the
async submit->poll path.
"""

import base64
import json
import os
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest
from PIL import Image

from hermes.ports.video_generation import VideoGenerationRequest
from providers.vertex_video_provider import GoogleVertexVideoProvider
from providers.video_provider_factory import get_video_provider


@pytest.fixture(autouse=True)
def _allow_fake(monkeypatch):
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


def _response(body: dict, status: int = 200) -> mock.Mock:
    resp = mock.Mock()
    resp.status_code = status
    resp.json = lambda: body
    resp.text = json.dumps(body)
    return resp


OP_NAME = "projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-generate-001/operations/123456"


def test_video_factory_provider_selection(workspace: Path, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "fake")
    provider = get_video_provider(str(workspace))
    from providers.fake_video_provider import FakeVideoGenerationProvider
    assert isinstance(provider, FakeVideoGenerationProvider)

    monkeypatch.setenv("VIDEO_PROVIDER", "google_vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    provider = get_video_provider(str(workspace))
    assert isinstance(provider, GoogleVertexVideoProvider)


def test_vertex_video_submit_async(workspace: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("VIDEO_MODEL", "veo-3.1-generate-001")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_video_provider.get_access_token", lambda: "tok")

    provider = GoogleVertexVideoProvider()
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _response({"name": OP_NAME})

    with mock.patch("providers.vertex_video_provider.requests.post", side_effect=fake_post):
        result = provider.generate(
            VideoGenerationRequest(
                request_id="vscene_1", owner_user_id="owner", scene_id="s1",
                prompt="camera pans over a blue bottle", duration_seconds=4,
                aspect_ratio="9:16",
            )
        )

    assert result.success is True
    assert result.video_path is None
    assert result.provider_operation_id == OP_NAME
    assert "predictLongRunning" in captured["url"]
    assert captured["json"]["parameters"]["aspectRatio"] == "9:16"
    assert captured["json"]["parameters"]["durationSeconds"] == 4
    assert captured["json"]["instances"][0]["prompt"].startswith("camera pans")


def test_vertex_video_submit_with_reference_image(workspace: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_video_provider.get_access_token", lambda: "tok")

    ref = tmp_path / "frame.png"
    ref.write_bytes(b"\x89PNG\r\n\x1a\nframe")

    provider = GoogleVertexVideoProvider()
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _response({"name": OP_NAME})

    with mock.patch("providers.vertex_video_provider.requests.post", side_effect=fake_post):
        result = provider.generate(
            VideoGenerationRequest(
                request_id="vscene_2", owner_user_id="owner", scene_id="s2",
                prompt="motion", duration_seconds=3,
                reference_image_paths=(str(ref),),
                aspect_ratio="9:16",
            )
        )

    instance = captured["json"]["instances"][0]
    assert instance["image"]["bytesBase64Encoded"]
    assert base64.b64decode(instance["image"]["bytesBase64Encoded"]) == ref.read_bytes()


def test_vertex_video_normalizes_webp_by_magic_bytes(workspace: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_video_provider.get_access_token", lambda: "tok")

    reference = tmp_path / "mislabelled.png"
    Image.new("RGB", (2, 2), "red").save(reference, format="WEBP")
    assert reference.read_bytes()[8:12] == b"WEBP"
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _response({"name": OP_NAME})

    provider = GoogleVertexVideoProvider()
    with mock.patch("providers.vertex_video_provider.requests.post", side_effect=fake_post):
        result = provider.generate(
            VideoGenerationRequest(
                request_id="webp-ref", owner_user_id="owner", scene_id="scene",
                prompt="motion", duration_seconds=5,
                reference_image_paths=(str(reference),),
            )
        )

    image = captured["json"]["instances"][0]["image"]
    normalized = base64.b64decode(image["bytesBase64Encoded"])
    assert result.success is True
    assert image["mimeType"] == "image/png"
    assert normalized.startswith(b"\x89PNG\r\n\x1a\n")
    assert captured["json"]["parameters"]["durationSeconds"] == 6


def test_vertex_video_detects_png_independent_of_extension(workspace: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_video_provider.get_access_token", lambda: "tok")

    reference = tmp_path / "mislabelled.webp"
    Image.new("RGB", (2, 2), "blue").save(reference, format="PNG")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _response({"name": OP_NAME})

    provider = GoogleVertexVideoProvider()
    with mock.patch("providers.vertex_video_provider.requests.post", side_effect=fake_post):
        provider.generate(
            VideoGenerationRequest(
                request_id="png-ref", owner_user_id="owner", scene_id="scene",
                prompt="motion", duration_seconds=8,
                reference_image_paths=(str(reference),),
            )
        )

    image = captured["json"]["instances"][0]["image"]
    assert image["mimeType"] == "image/png"
    assert base64.b64decode(image["bytesBase64Encoded"]) == reference.read_bytes()


def test_vertex_video_submit_error_normalized(workspace: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_video_provider.get_access_token", lambda: "tok")

    provider = GoogleVertexVideoProvider()
    error_body = {"error": {"message": "Publisher model not found"}}

    with mock.patch(
        "providers.vertex_video_provider.requests.post",
        return_value=_response(error_body, status=404),
    ):
        result = provider.generate(
            VideoGenerationRequest(request_id="x", owner_user_id="o", scene_id="s", prompt="p", duration_seconds=3)
        )

    assert result.success is False
    assert "404" in result.error_message
    assert "Publisher model not found" in result.error_message


def test_vertex_video_check_running_then_completed(workspace: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_video_provider.get_access_token", lambda: "tok")

    video_bytes = b"\x00\x00\x00\x18ftypmp42"
    encoded = base64.b64encode(video_bytes).decode("ascii")

    provider = GoogleVertexVideoProvider()
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _response({
            "name": OP_NAME,
            "done": True,
            "response": {"videos": [{"bytesBase64Encoded": encoded, "mimeType": "video/mp4"}]},
        })

    with mock.patch("providers.vertex_video_provider.requests.post", side_effect=fake_post):
        result = provider.check_status(OP_NAME)

    assert result.success is True
    assert result.video_path is not None
    assert Path(result.video_path).exists()
    assert Path(result.video_path).read_bytes() == video_bytes
    assert "fetchPredictOperation" in captured["url"]
    assert captured["json"] == {"operationName": OP_NAME}


def test_vertex_video_check_still_running(workspace: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_video_provider.get_access_token", lambda: "tok")

    provider = GoogleVertexVideoProvider()

    with mock.patch(
        "providers.vertex_video_provider.requests.post",
        return_value=_response({"name": OP_NAME, "done": False}),
    ):
        result = provider.check_status(OP_NAME)

    assert result.success is True
    assert result.video_path is None
    assert result.metadata["status"] == "running"


# ============================================================================
# Worker video_generate integration (fake provider)
# ============================================================================


def test_worker_video_generate_sync_completes(tmp_path: Path, monkeypatch):
    from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
    from hermes.domain.job import Job
    from workers.job_worker import CanonicalJobWorker

    monkeypatch.setenv("VIDEO_PROVIDER", "fake")

    db_path = tmp_path / "jobs.db"
    workspace = tmp_path / "workspace"
    worker = CanonicalJobWorker(str(db_path), str(workspace))

    repo = CanonicalJobRepository(str(db_path))
    job = Job.new("video_generate", {
        "owner_user_id": "owner",
        "request_id": "scene_v1",
        "scene_id": "s1",
        "prompt": "a blue bottle spins",
        "duration_seconds": 3,
        "aspect_ratio": "9:16",
    })
    repo.submit(job)

    result = worker.run_once()
    assert result["state"] == "completed"
    payload = result["result"]
    assert payload["task_type"] == "video_generate"
    assert payload["output_path"]
    assert Path(payload["output_path"]).exists()
    assert str(Path(payload["output_path"]).resolve()).startswith(str(workspace.resolve()))


def test_worker_video_generate_async_submit_then_poll(tmp_path: Path, monkeypatch):
    """Async path: first claim submits + persists op, second claim completes."""
    from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
    from hermes.domain.job import Job
    from hermes.ports.video_generation import VideoGenerationResult
    from providers.fake_video_provider import FakeVideoGenerationProvider
    from workers.job_worker import CanonicalJobWorker

    class AsyncFakeProvider(FakeVideoGenerationProvider):
        def __init__(self, output_dir=None):
            super().__init__(output_dir)
            self._submitted = False

        def generate(self, request):
            self._submitted = True
            return VideoGenerationResult(
                request_id=request.request_id, success=True,
                video_path=None, provider_operation_id="op_async_1",
                metadata={"provider": "fake_async", "status": "submitted"},
            )

        def check_status(self, operation_id):
            if not self._submitted:
                return VideoGenerationResult(request_id=operation_id, success=False,
                                             error_message="not submitted")
            video = super().generate(VideoGenerationRequest(
                request_id=f"async_{operation_id}", owner_user_id="owner", scene_id="s1",
                prompt="x", duration_seconds=2))
            return VideoGenerationResult(
                request_id=operation_id, success=True, video_path=video.video_path,
                provider_operation_id=operation_id,
                metadata={"provider": "fake_async", "status": "completed"},
            )

    db_path = tmp_path / "jobs.db"
    workspace = tmp_path / "workspace"
    worker = CanonicalJobWorker(str(db_path), str(workspace))

    # Inject async provider via factory patch
    monkeypatch.setenv("VIDEO_PROVIDER", "fake")
    import providers.video_provider_factory as vpf
    provider_holder = {}

    def factory(output_dir=None):
        if provider_holder.get("p") is None:
            provider_holder["p"] = AsyncFakeProvider(output_dir)
        return provider_holder["p"]

    monkeypatch.setattr(vpf, "get_video_provider", factory)

    repo = CanonicalJobRepository(str(db_path))
    job = Job.new("video_generate", {
        "owner_user_id": "owner", "request_id": "scene_a", "scene_id": "s1",
        "prompt": "spin", "duration_seconds": 2,
    })
    repo.submit(job)

    # Claim 1: submit + persist operation id -> retryable requeue
    result = worker.run_once()
    assert result["state"] == "queued"
    assert result.get("payload", {}).get("provider_operation_id") == "op_async_1"

    # Claim 2: resume, check_status -> completed
    result = worker.run_once()
    assert result["state"] == "completed"
    payload = result["result"]
    assert payload["provider_operation_id"] == "op_async_1"
    assert payload["output_path"]
    assert Path(payload["output_path"]).exists()
