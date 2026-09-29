from __future__ import annotations

import base64
import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hermes_personal.integrations.video_factory.keyframe_provider import (
    KeyframeOperationStore,
    KeyframeRuntime,
    VertexKeyframeProvider,
)
from hermes_personal.integrations.video_factory.ports import (
    KeyframeGenerationRequest,
    KeyframeGenerationResult,
)
from hermes_personal.product_video.qc.keyframe_qc import run_keyframe_qc
from hermes_personal.product_video.qc.models import NormalizedProduct, QCVerdict


def _request(reference: Path) -> KeyframeGenerationRequest:
    return KeyframeGenerationRequest(
        operation_id="keyframe-pv-1-scene-1",
        workflow_id="pv-1",
        project_id="project-1",
        frame_id="scene-1-start",
        prompt="Create a real-life desk scene with Baseus Bowie WM02 product [1].",
        product_description="Baseus Bowie WM02 wireless earbuds and charging case",
        reference_image_paths=(str(reference),),
        aspect_ratio="9:16",
    )


def test_vertex_keyframe_provider_uses_product_references_and_writes_image(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"source-image")
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"generated"
    calls: list[dict[str, Any]] = []

    def post(url: str, **kwargs: Any) -> Any:
        calls.append({"url": url, **kwargs})
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
            "candidates": [{
                "content": {"parts": [{"inlineData": {
                    "data": base64.b64encode(png_bytes).decode(),
                    "mimeType": "image/png",
                }}]}
            }]
            },
        )

    result = VertexKeyframeProvider(
        project_id="gen-lang-client-0816609628",
        output_dir=tmp_path / "keyframes",
        credential_resolver=lambda: ("token", "ignored"),
        post_fn=post,
    ).submit(_request(reference))

    assert result.status == "completed"
    assert Path(result.image_path or "").read_bytes() == png_bytes
    body = calls[0]["json"]
    assert body["generationConfig"]["imageConfig"]["aspectRatio"] == "9:16"
    assert body["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "image/jpeg"
    assert "seller" in body["contents"][0]["parts"][0]["text"]


class _ResumableProvider:
    def __init__(self, completed_path: Path) -> None:
        self.completed_path = completed_path
        self.submit_calls: list[str] = []
        self.poll_calls: list[str] = []

    def submit(self, request: KeyframeGenerationRequest) -> KeyframeGenerationResult:
        self.submit_calls.append(request.operation_id)
        raise AssertionError("resume must not resubmit")

    def get_status(self, operation_id: str) -> KeyframeGenerationResult:
        self.poll_calls.append(operation_id)
        return KeyframeGenerationResult(
            operation_id="keyframe-pv-1-scene-1",
            status="completed",
            provider_operation_id=operation_id,
            image_path=str(self.completed_path),
        )


def test_resume_polls_existing_keyframe_operation_without_resubmit(tmp_path: Path) -> None:
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"source-image")
    completed = tmp_path / "generated.png"
    completed.write_bytes(b"generated-image")
    connection = sqlite3.connect(":memory:")
    store = KeyframeOperationStore(connection)
    request = _request(reference)
    store.save_result(
        request,
        KeyframeGenerationResult(
            operation_id=request.operation_id,
            status="running",
            provider_operation_id="operations/kf-1",
        ),
    )
    provider = _ResumableProvider(completed)

    result = KeyframeRuntime(store=store, provider=provider).run(request)

    assert result.status == "completed"
    assert provider.submit_calls == []
    assert provider.poll_calls == ["operations/kf-1"]
    saved = store.get(request.operation_id)
    assert saved is not None
    assert saved["output_sha256"] == hashlib.sha256(completed.read_bytes()).hexdigest()


def test_runtime_keeps_terminal_failure_on_same_attempt(tmp_path: Path) -> None:
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"source-image")
    connection = sqlite3.connect(":memory:")
    store = KeyframeOperationStore(connection)
    request = _request(reference)

    class RetryProvider:
        def __init__(self) -> None:
            self.submit_calls: list[str] = []

        def submit(self, req: KeyframeGenerationRequest) -> KeyframeGenerationResult:
            self.submit_calls.append(req.operation_id)
            return KeyframeGenerationResult(
                operation_id=req.operation_id,
                status="completed",
                provider_operation_id=req.operation_id,
            )

        def get_status(self, _: str) -> KeyframeGenerationResult:
            raise AssertionError("failed operation must not be polled")

    store.save_result(
        request,
        KeyframeGenerationResult(
            operation_id=request.operation_id,
            status="failed",
            error_code="HTTP_404",
            error_message="model unavailable",
        ),
    )
    provider = RetryProvider()

    result = KeyframeRuntime(store=store, provider=provider).run(request)

    assert result.status == "failed"
    assert result.error_code == "HTTP_404"
    assert provider.submit_calls == []


def test_two_sqlite_workers_claim_one_first_keyframe_submission(tmp_path: Path) -> None:
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"source-image")
    request = _request(reference)
    db_path = tmp_path / "keyframe-claims.sqlite"
    KeyframeOperationStore(sqlite3.connect(db_path)).connection.close()
    barrier = threading.Barrier(2)
    calls: list[str] = []
    results: list[KeyframeGenerationResult] = []

    class CountedProvider:
        def submit(self, req: KeyframeGenerationRequest) -> KeyframeGenerationResult:
            calls.append(req.operation_id)
            time.sleep(0.1)
            return KeyframeGenerationResult(
                operation_id=req.operation_id, status="running",
                provider_operation_id="external-operation-1",
            )

        def get_status(self, operation_id: str) -> KeyframeGenerationResult:
            return KeyframeGenerationResult(
                operation_id=request.operation_id, status="running",
                provider_operation_id=operation_id,
            )

    provider = CountedProvider()

    def worker() -> None:
        connection = sqlite3.connect(db_path)
        runtime = KeyframeRuntime(store=KeyframeOperationStore(connection), provider=provider)
        barrier.wait()
        results.append(runtime.run(request))
        connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert calls == [request.operation_id]
    assert len(results) == 2
    assert {result.status for result in results} <= {"running", "unknown"}
    connection = sqlite3.connect(db_path)
    stored = KeyframeOperationStore(connection).get(request.operation_id)
    assert stored is not None
    assert stored["provider_operation_id"] == "external-operation-1"
    connection.close()


def test_keyframe_qc_requires_every_generated_frame_to_pass(tmp_path: Path) -> None:
    reference = tmp_path / "reference.jpg"
    keyframe = tmp_path / "keyframe.png"
    reference.write_bytes(b"reference")
    keyframe.write_bytes(b"keyframe")

    class Evaluator:
        fake_mode = True
        evaluator_name = "fake"
        evaluator_version = "1"
        model = "fake-vision"

        def evaluate_multiple_images(self, *_: Any, **__: Any) -> dict[str, Any]:
            return {
                "identity_consistency": 46,
                "scene_adherence": 27,
                "visual_cleanliness": 18,
                "total_score": 91,
                "verdict": "pass",
                "hard_failure": False,
                "source_branding_detected": False,
                "identity_mismatch": False,
                "prompt_reference_consistent": True,
                "important_details_preserved": True,
                "composition_usable": True,
                "animation_suitable": True,
                "recommended_action": "none",
                "reason": "grounded and clean",
            }

    report = run_keyframe_qc(
        workflow_id="pv-1",
        package={
            "storyboard_id": "story-1",
            "package_digest": "sha256:" + "a" * 64,
            "version": 1,
            "owner_user_id": "owner-pv-1",
            "project_id": "project-1",
            "generated_keyframes": [
                {
                    "frame_id": "scene-1-start",
                    "scene_id": "scene-1",
                    "image_path": str(keyframe),
                    "sha256": hashlib.sha256(keyframe.read_bytes()).hexdigest(),
                    "prompt": "User places earbuds into charging case",
                    "reference_image_paths": [str(reference)],
                }
            ],
        },
        product=NormalizedProduct(brand="Baseus", model="Bowie WM02"),
        evaluator=Evaluator(),
    )

    assert report.verdict == QCVerdict.PASS
    assert report.score == 91
    assert report.findings["items"][0]["verdict"] == "pass"
    assert report.findings["items"][0]["sha256"] == hashlib.sha256(
        keyframe.read_bytes()
    ).hexdigest()
    assert report.findings["items"][0]["reference_digests"] == [
        hashlib.sha256(reference.read_bytes()).hexdigest()
    ]
