"""PIMG1 tests: real image provider adapter + worker image_generate handler.

Gemini adapter tests mock the HTTP layer (no paid calls). Worker tests use
the deterministic fake provider.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from hermes.ports.image_generation import ImageGenerationRequest
from providers.gemini_image_provider import GeminiImageProvider
from providers.vertex_image_provider import GoogleVertexImageProvider, vertex_endpoint


@pytest.fixture(autouse=True)
def _allow_fake(monkeypatch):
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def ref_image(tmp_path: Path) -> Path:
    img = tmp_path / "ref.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return img


# ============================================================================
# Gemini adapter
# ============================================================================


def _fake_response(body: dict, status: int = 200) -> mock.Mock:
    resp = mock.Mock()
    resp.status_code = status
    resp.json = lambda: body
    resp.text = json.dumps(body)
    return resp


def _image_body(data: str) -> dict:
    return {
        "candidates": [
            {"content": {"parts": [{"inlineData": {"data": data}}]}}
        ]
    }


def test_gemini_generate_success(workspace: Path, ref_image: Path, monkeypatch):
    png = b"\x89PNG\r\n\x1a\ngenerated"
    encoded = __import__("base64").b64encode(png).decode("ascii")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_MODEL", "gemini-2.5-flash-image")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))

    provider = GeminiImageProvider()
    captured = {}

    def fake_post(url, params=None, json=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["json"] = json
        return _fake_response(_image_body(encoded))

    with mock.patch("providers.gemini_image_provider.requests.post", side_effect=fake_post):
        request = ImageGenerationRequest(
            request_id="frame_abc",
            owner_user_id="owner",
            positive_prompt="blue water bottle on a table",
            negative_prompt="text, watermark",
            reference_image_paths=(str(ref_image),),
            aspect_ratio="9:16",
        )
        result = provider.generate(request)

    assert result.success is True
    assert len(result.image_paths) == 1
    assert Path(result.image_paths[0]).exists()
    assert Path(result.image_paths[0]).read_bytes() == png

    # Request body: reference image inline part then text part
    contents = captured["json"]["contents"]
    parts = contents[0]["parts"]
    assert contents[0]["role"] == "user"
    assert parts[0]["inlineData"]["mimeType"] == "image/png"
    assert "water bottle" in parts[1]["text"]
    # Negative prompt is not appended (image models have no negative semantics)
    assert "Avoid:" not in parts[1]["text"]
    # Aspect ratio passed via imageConfig
    assert captured["json"]["generationConfig"]["imageConfig"]["aspectRatio"] == "9:16"
    # Key sent as query param, not in body
    assert captured["params"]["key"] == "test-key"


def test_gemini_generate_idempotent(workspace: Path, monkeypatch):
    png = b"\x89PNG\r\n\x1a\ngenerated"
    encoded = __import__("base64").b64encode(png).decode("ascii")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_MODEL", "gemini-2.5-flash-image")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))

    provider = GeminiImageProvider()
    calls = {"count": 0}

    def fake_post(url, params=None, json=None, timeout=None):
        calls["count"] += 1
        return _fake_response(_image_body(encoded))

    request = ImageGenerationRequest(
        request_id="frame_dup", owner_user_id="owner", positive_prompt="prompt"
    )
    with mock.patch("providers.gemini_image_provider.requests.post", side_effect=fake_post):
        first = provider.generate(request)
        second = provider.generate(request)

    assert first.success is True and second.success is True
    # Second call served from cache, no API call
    assert calls["count"] == 1
    assert second.metadata["idempotent"] is True


def test_gemini_generate_error_normalization(workspace: Path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_MODEL", "gemini-2.5-flash-image")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))

    provider = GeminiImageProvider()
    error_body = {"error": {"message": "quota exceeded"}}

    with mock.patch(
        "providers.gemini_image_provider.requests.post",
        return_value=_fake_response(error_body, status=429),
    ):
        result = provider.generate(
            ImageGenerationRequest(request_id="frame_err", owner_user_id="owner", positive_prompt="p")
        )

    assert result.success is False
    assert "429" in result.error_message
    assert "quota exceeded" in result.error_message


def test_gemini_generate_requires_key(workspace: Path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiImageProvider()


def test_gemini_output_within_workspace(workspace: Path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_MODEL", "gemini-2.5-flash-image")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))

    from providers.gemini_common import output_path_for

    provider = GeminiImageProvider()
    output = output_path_for(provider.output_dir, "frame_x")
    # Output path is under the configured workspace
    assert str(output.resolve()).startswith(str(workspace.resolve()))


# ============================================================================
# Vertex adapter
# ============================================================================


def test_vertex_endpoint_url():
    url = vertex_endpoint("gen-lang-client-0816609628", "global", "gemini-3.1-flash-lite-image")
    assert url == (
        "https://global-aiplatform.googleapis.com/v1/projects/gen-lang-client-0816609628"
        "/locations/global/publishers/google/models/gemini-3.1-flash-lite-image:generateContent"
    )


def test_vertex_generate_success(workspace: Path, monkeypatch):
    png = b"\x89PNG\r\n\x1a\ngenerated-vertex"
    encoded = __import__("base64").b64encode(png).decode("ascii")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.setenv("IMAGE_MODEL", "gemini-3.1-flash-lite-image")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_image_provider.get_access_token", lambda: "fake-token")

    provider = GoogleVertexImageProvider()

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _fake_response(_image_body(encoded))

    with mock.patch("providers.vertex_image_provider.requests.post", side_effect=fake_post):
        request = ImageGenerationRequest(
            request_id="vframe_1",
            owner_user_id="owner",
            positive_prompt="blue bottle on table",
            aspect_ratio="9:16",
        )
        result = provider.generate(request)

    assert result.success is True
    assert len(result.image_paths) == 1
    assert Path(result.image_paths[0]).read_bytes() == png
    assert captured["headers"]["Authorization"] == "Bearer fake-token"
    assert "gen-lang-client-0816609628" in captured["url"]
    assert "gemini-3.1-flash-lite-image" in captured["url"]
    assert captured["json"]["generationConfig"]["imageConfig"]["aspectRatio"] == "9:16"
    assert captured["json"]["contents"][0]["parts"][-1]["text"].startswith("blue bottle")


def test_vertex_generate_idempotent(workspace: Path, monkeypatch):
    png = b"\x89PNG\r\n\x1a\nv"
    encoded = __import__("base64").b64encode(png).decode("ascii")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_image_provider.get_access_token", lambda: "fake-token")

    provider = GoogleVertexImageProvider()
    calls = {"count": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["count"] += 1
        return _fake_response(_image_body(encoded))

    request = ImageGenerationRequest(request_id="vdup", owner_user_id="owner", positive_prompt="p")
    with mock.patch("providers.vertex_image_provider.requests.post", side_effect=fake_post):
        provider.generate(request)
        second = provider.generate(request)

    assert calls["count"] == 1
    assert second.metadata["idempotent"] is True


def test_vertex_generate_error_normalization(workspace: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_image_provider.get_access_token", lambda: "fake-token")

    provider = GoogleVertexImageProvider()
    error_body = {"error": {"message": "permission denied"}}

    with mock.patch(
        "providers.vertex_image_provider.requests.post",
        return_value=_fake_response(error_body, status=403),
    ):
        result = provider.generate(
            ImageGenerationRequest(request_id="vframe_err", owner_user_id="owner", positive_prompt="p")
        )

    assert result.success is False
    assert "403" in result.error_message
    assert "permission denied" in result.error_message


def test_vertex_generate_requires_project(workspace: Path, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        GoogleVertexImageProvider()


def test_vertex_generate_reports_auth_failure(workspace: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))

    def raise_auth():
        raise RuntimeError("Could not automatically determine credentials")

    monkeypatch.setattr("providers.vertex_image_provider.get_access_token", raise_auth)

    provider = GoogleVertexImageProvider()
    result = provider.generate(
        ImageGenerationRequest(request_id="vauth", owner_user_id="owner", positive_prompt="p")
    )
    assert result.success is False
    assert "credentials" in result.error_message.lower()


def test_vertex_generate_sends_reference_image_bytes(workspace: Path, tmp_path: Path, monkeypatch):
    """Reference product image bytes + prompt must both reach the Vertex request."""
    import base64 as b64

    png = b"\x89PNG\r\n\x1a\nREF-BYTES"
    ref = tmp_path / "product_ref.png"
    ref.write_bytes(png)
    encoded = b64.b64encode(png).decode("ascii")

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setattr("providers.vertex_image_provider.get_access_token", lambda: "tok")

    provider = GoogleVertexImageProvider()
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _fake_response(_image_body(encoded))

    with mock.patch("providers.vertex_image_provider.requests.post", side_effect=fake_post):
        result = provider.generate(ImageGenerationRequest(
            request_id="ref_1", owner_user_id="owner",
            positive_prompt="keep product identity",
            reference_image_paths=(str(ref),),
            aspect_ratio="9:16",
        ))

    assert result.success is True
    parts = captured["json"]["contents"][0]["parts"]
    # reference image inline part first, prompt text last
    inline = next(p for p in parts if "inlineData" in p)
    assert inline["inlineData"]["mimeType"] == "image/png"
    assert inline["inlineData"]["data"] == encoded
    assert parts[-1]["text"] == "keep product identity"


def test_worker_image_job_resolves_resource_reference(tmp_path, monkeypatch):
    """Worker image_generate must pass real reference image paths to the provider."""
    from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
    from hermes.domain.job import Job
    from workers.job_worker import CanonicalJobWorker

    monkeypatch.setenv("IMAGE_PROVIDER", "fake")
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")
    db_path = tmp_path / "jobs.db"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    worker = CanonicalJobWorker(str(db_path), str(workspace))
    repo = CanonicalJobRepository(str(db_path))

    ref = workspace / "products" / "ref.png"
    ref.parent.mkdir()
    ref.write_bytes(b"\x89PNG\r\n\x1a\nref")

    job = Job.new("image_generate", {
        "owner_user_id": "o", "request_id": "p_f1", "prompt": "keep product",
        "reference_image_paths": [str(ref)],
    })
    repo.submit(job)
    result = worker.run_once()
    assert result["state"] == "completed"
    # fake provider wrote the output; reference path was accepted (no error)
    assert result["error"] == ""



# ============================================================================
# Worker image_generate handler (fake provider)
# ============================================================================


def test_worker_image_generate_with_fake_provider(tmp_path: Path, monkeypatch):
    from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
    from hermes.application.video_service import VideoService
    from hermes.domain.job import Job, JobStatus
    from workers.job_worker import CanonicalJobWorker

    monkeypatch.setenv("IMAGE_PROVIDER", "fake")

    db_path = tmp_path / "jobs.db"
    workspace = tmp_path / "workspace"
    worker = CanonicalJobWorker(str(db_path), str(workspace))

    repo = CanonicalJobRepository(str(db_path))
    job = Job.new("image_generate", {
        "owner_user_id": "owner",
        "request_id": "frame_w1",
        "prompt": "blue bottle on table",
        "negative_prompt": "",
        "aspect_ratio": "9:16",
    })
    repo.submit(job)

    result = worker.run_once()
    assert result is not None
    assert result["state"] == "completed"

    payload_result = result["result"]
    assert payload_result["task_type"] == "image_generate"
    assert len(payload_result["output_paths"]) == 1
    output_path = Path(payload_result["output_paths"][0])
    # Asset inside workspace
    assert str(output_path.resolve()).startswith(str(workspace.resolve()))
    assert output_path.exists()


def test_worker_image_generate_rejects_bad_payload(tmp_path: Path, monkeypatch):
    from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
    from hermes.domain.job import Job
    from workers.job_worker import CanonicalJobWorker

    monkeypatch.setenv("IMAGE_PROVIDER", "fake")

    db_path = tmp_path / "jobs.db"
    workspace = tmp_path / "workspace"
    worker = CanonicalJobWorker(str(db_path), str(workspace))

    repo = CanonicalJobRepository(str(db_path))
    job = Job.new("image_generate", {"owner_user_id": "owner"})  # missing prompt/request_id
    repo.submit(job)

    result = worker.run_once()
    assert result["state"] == "failed"
    assert "request_id" in (result["error"] or "")