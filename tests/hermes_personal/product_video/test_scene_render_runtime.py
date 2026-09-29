from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from hermes_personal.integrations.video_factory.ports import (
    VideoGenerationRequest,
    VideoGenerationResult,
)
from hermes_personal.integrations.video_factory.scene_renderer import (
    SceneRenderOperationStore,
    SceneRenderRuntime,
    compile_grounded_scene_request,
)
from hermes_personal.product_video.creative.storyboard import storyboard_package_digest


def _request(keyframe: Path, *, duration: int = 4) -> VideoGenerationRequest:
    keyframe_sha = hashlib.sha256(keyframe.read_bytes()).hexdigest()
    source_sha = "b" * 64
    return compile_grounded_scene_request(
        owner_user_id="operator-1",
        workflow_id="workflow-1",
        project_id="project-1",
        scene={
            "scene_id": "scene-01",
            "duration_seconds": duration,
            "subject_action": "A commuter takes one earbud from the charging case",
            "product_interaction": "The hand lifts the right earbud naturally",
            "start_state": "Both earbuds rest inside the open charging case",
            "end_state": "One earbud is held beside the open case",
            "visual_change": "The right earbud moves from the case into the commuter's hand",
            "environment": "A clean morning commute desk",
            "camera_framing": "Medium close-up",
            "camera_movement": "Subtle handheld tracking",
            "overlay_text": "Pin 25 giờ",
        },
        keyframe={
            "frame_id": "scene-01-start",
            "scene_id": "scene-01",
            "image_path": str(keyframe),
            "sha256": keyframe_sha,
            "reference_sha256s": [source_sha],
        },
        keyframe_qc_receipt={
            "stage": "keyframe",
            "verdict": "pass",
            "score": 92,
            "artifact_digest": "sha256:approved-package",
            "findings": {
                "items": [
                    {
                        "frame_id": "scene-01-start",
                        "sha256": keyframe_sha,
                        "reference_digests": [source_sha],
                        "score": 92,
                        "verdict": "pass",
                        "hard_failure": False,
                    }
                ]
            },
        },
        package_digest="sha256:approved-package",
        product_identity="Baseus Bowie WM02 wireless earbuds",
        provider_model="veo-3.1-generate-001",
    )


def test_compile_scene_uses_only_generated_keyframe_and_excludes_overlay_text(
    tmp_path: Path,
) -> None:
    keyframe = tmp_path / "generated-keyframe.png"
    keyframe.write_bytes(b"generated-keyframe")

    request = _request(keyframe)

    assert request.reference_image_paths == (str(keyframe.resolve()),)
    assert "takes one earbud" in request.prompt
    assert "Both earbuds rest" in request.prompt
    assert "One earbud is held" in request.prompt
    assert "right earbud moves" in request.prompt
    assert "Pin 25 giờ" not in request.prompt
    assert "watermark" in request.provider_options["negativePrompt"]
    assert "marketplace UI" in request.provider_options["negativePrompt"]
    assert "source-store branding" in request.provider_options["negativePrompt"]
    assert "Minh Gear" not in request.provider_options["negativePrompt"]


def test_compiled_scene_requests_approved_narration_without_requiring_audio(tmp_path: Path) -> None:
    keyframe = tmp_path / "generated-keyframe.png"
    keyframe.write_bytes(b"generated-keyframe")
    source_sha = "b" * 64
    keyframe_sha = hashlib.sha256(keyframe.read_bytes()).hexdigest()
    request = compile_grounded_scene_request(
        owner_user_id="operator-1",
        workflow_id="workflow-audio",
        project_id="project-1",
        scene={
            "scene_id": "scene-01",
            "duration_seconds": 4,
            "subject_action": "A commuter lifts one earbud",
            "product_interaction": "The hand lifts the earbud from its case",
            "start_state": "Both earbuds are in the open case",
            "end_state": "One earbud is held beside the case",
            "visual_change": "The earbud moves into the hand",
            "environment": "Morning desk",
            "narration": "Cất gọn tai nghe chỉ với một thao tác.",
        },
        keyframe={
            "frame_id": "scene-01-start",
            "scene_id": "scene-01",
            "image_path": str(keyframe),
            "sha256": keyframe_sha,
            "reference_sha256s": [source_sha],
        },
        keyframe_qc_receipt={
            "stage": "keyframe",
            "verdict": "pass",
            "score": 92,
            "artifact_digest": "sha256:approved-package",
            "findings": {"items": [{
                "frame_id": "scene-01-start",
                "sha256": keyframe_sha,
                "reference_digests": [source_sha],
                "score": 92,
                "verdict": "pass",
                "hard_failure": False,
            }]},
        },
        package_digest="sha256:approved-package",
        product_identity="Baseus Bowie WM02",
        provider_model="veo-3.1-generate-001",
    )
    assert request.request_audio is True
    assert "Cất gọn tai nghe chỉ với một thao tác." in request.prompt
    assert "Do not add subtitles" in request.prompt


@pytest.mark.parametrize(
    ("receipt_patch", "message"),
    [
        ({"verdict": "fail"}, "QC PASS"),
        ({"score": 79}, "score"),
        ({"hard_failure": True}, "hard failure"),
        ({"artifact_digest": "sha256:stale"}, "digest"),
    ],
)
def test_compile_scene_rejects_stale_or_failed_keyframe_qc(
    tmp_path: Path, receipt_patch: dict[str, object], message: str
) -> None:
    keyframe = tmp_path / "generated-keyframe.png"
    keyframe.write_bytes(b"generated-keyframe")
    keyframe_sha = hashlib.sha256(keyframe.read_bytes()).hexdigest()
    source_sha = "b" * 64
    receipt = {
        "stage": "keyframe",
        "verdict": "pass",
        "score": 92,
        "artifact_digest": "sha256:approved-package",
        "findings": {
            "items": [
                {
                    "frame_id": "scene-01-start",
                    "sha256": keyframe_sha,
                    "reference_digests": [source_sha],
                    "score": 92,
                    "verdict": "pass",
                    "hard_failure": False,
                }
            ]
        },
    }
    receipt.update(receipt_patch)

    with pytest.raises(ValueError, match=message):
        compile_grounded_scene_request(
            owner_user_id="operator-1",
            workflow_id="workflow-1",
            project_id="project-1",
            scene={
                "scene_id": "scene-01",
                "duration_seconds": 4,
                "subject_action": "A commuter takes one earbud from the case",
                "product_interaction": "The hand lifts the earbud",
                "start_state": "Earbuds rest in the open case",
                "end_state": "One earbud is held beside the case",
                "visual_change": "One earbud moves into the hand",
                "environment": "Morning commute desk",
                "camera_framing": "Medium close-up",
                "camera_movement": "Subtle handheld tracking",
            },
            keyframe={
                "frame_id": "scene-01-start",
                "scene_id": "scene-01",
                "image_path": str(keyframe),
                "sha256": keyframe_sha,
                "reference_sha256s": [source_sha],
            },
            keyframe_qc_receipt=receipt,
            package_digest="sha256:approved-package",
            product_identity="Baseus Bowie WM02 wireless earbuds",
            provider_model="veo-3.1-generate-001",
        )


@pytest.mark.parametrize("duration", [3, 5, 7, 10])
def test_compile_scene_rejects_unsupported_duration_before_submit(
    tmp_path: Path, duration: int
) -> None:
    keyframe = tmp_path / "generated-keyframe.png"
    keyframe.write_bytes(b"generated-keyframe")

    with pytest.raises(ValueError, match="allowed values are 4, 6, 8"):
        _request(keyframe, duration=duration)


def test_scene_operation_id_is_deterministic_sha256(tmp_path: Path) -> None:
    keyframe = tmp_path / "generated-keyframe.png"
    keyframe.write_bytes(b"generated-keyframe")

    first = _request(keyframe)
    second = _request(keyframe)

    assert first.request_id == second.request_id
    assert first.request_id == "video-scene-" + hashlib.sha256(
        (
            "workflow-1|scene-01|sha256:approved-package|"
            "veo-3.1-generate-001|4"
        ).encode()
    ).hexdigest()[:24]


class _ResumeProvider:
    provider_kind = "google_flow"

    def __init__(self, provider_kind: str = "google_flow") -> None:
        self.provider_kind = provider_kind
        self.submit_calls: list[str] = []
        self.poll_calls: list[str] = []

    def submit(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        self.submit_calls.append(request.request_id)
        raise AssertionError("resume must not submit another paid operation")

    def get_status(self, operation_id: str) -> VideoGenerationResult:
        self.poll_calls.append(operation_id)
        return VideoGenerationResult(
            request_id=operation_id,
            status="running",
            provider_operation_id=operation_id,
        )


def test_vertex_resume_polls_the_durably_pinned_official_provider(tmp_path: Path) -> None:
    keyframe = tmp_path / "generated-keyframe.png"
    keyframe.write_bytes(b"generated-keyframe")
    request = _request(keyframe)
    store = SceneRenderOperationStore(sqlite3.connect(":memory:"))
    store.mark_planned(request)
    store.claim_provider_for_submission(request, "vertex_ai")
    store.save_result(
        request,
        VideoGenerationResult(
            request_id=request.request_id,
            status="submitted",
            provider_operation_id="operations/video-scene-01",
        ),
    )
    provider = _ResumeProvider("vertex_ai")

    result = SceneRenderRuntime(store=store, provider=provider).run(request)

    assert result.status == "running"
    assert provider.submit_calls == []
    assert provider.poll_calls == ["operations/video-scene-01"]


def test_checkpoint_without_provider_id_refuses_ambiguous_resubmit(
    tmp_path: Path,
) -> None:
    keyframe = tmp_path / "generated-keyframe.png"
    keyframe.write_bytes(b"generated-keyframe")
    request = _request(keyframe)
    store = SceneRenderOperationStore(sqlite3.connect(":memory:"))
    store.mark_submitting(request)
    provider = _ResumeProvider()

    result = SceneRenderRuntime(store=store, provider=provider).run(request)

    assert result.status == "failed"
    assert result.error_code == "RECONCILIATION_REQUIRED"
    assert provider.submit_calls == []


def _render_fixture(tmp_path: Path):
    from hermes_personal.integrations.video_factory.domain import (
        AssetReference,
        FramePrompt,
        ProjectStatus,
        ResourcePack,
        Storyboard,
        StoryboardApprovalStatus,
        StoryboardFrame,
        VideoFactoryProject,
    )

    source = tmp_path / "raw-listing.jpg"
    source.write_bytes(b"raw-listing-image")
    keyframe = tmp_path / "generated-keyframe.png"
    keyframe.write_bytes(b"generated-keyframe")
    keyframe_sha = hashlib.sha256(keyframe.read_bytes()).hexdigest()
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    frame = StoryboardFrame(
        frame_id="scene-01-start",
        scene_id="scene-01",
        order=1,
        label="Real use",
        purpose="Show use",
        visual_state="Earbuds in case",
        subject_action="Take one earbud",
        product_state="Open case",
        character_state="Hand ready",
        context="Morning desk",
        camera_intention="Medium close-up",
        prompt=FramePrompt(
            positive_prompt="Legacy prompt that must not be used",
            reference_asset_ids=("source-1",),
        ),
    )
    project = VideoFactoryProject(
        id="project-1",
        owner_user_id="operator-1",
        status=ProjectStatus.STORYBOARD_APPROVED,
        resource_pack=ResourcePack(
            id="pack-1",
            owner_user_id="operator-1",
            product_references=(
                AssetReference("source-1", str(source), {"qc_eligible": True, "qc_sha256": source_sha}),
            ),
            primary_product_asset_id="source-1",
            product_identity_description="Baseus Bowie WM02 wireless earbuds",
        ),
        storyboard=Storyboard(
            storyboard_id="storyboard-1",
            project_id="project-1",
            frames=(frame,),
            approval_status=StoryboardApprovalStatus.APPROVED,
        ),
    )
    scene = {
        "scene_id": "scene-01",
        "duration_seconds": 4,
        "subject_action": "A commuter takes one earbud from the charging case",
        "product_interaction": "The hand lifts the right earbud naturally",
        "start_state": "Both earbuds rest inside the open charging case",
        "end_state": "One earbud is held beside the open case",
        "visual_change": "The right earbud moves from the case into the commuter's hand",
        "environment": "A clean morning commute desk",
        "camera_framing": "Medium close-up",
        "camera_movement": "Subtle handheld tracking",
        "overlay_text": "Pin 25 giờ",
    }
    keyframe_item = {
        "frame_id": "scene-01-start",
        "scene_id": "scene-01",
        "image_path": str(keyframe),
        "sha256": keyframe_sha,
        "reference_sha256s": [source_sha],
    }
    receipt = {
        "report_id": "qc-keyframe-1",
        "stage": "keyframe",
        "verdict": "pass",
        "score": 92,
        "artifact_digest": "sha256:approved-package",
        "findings": {
            "items": [
                {
                    "frame_id": "scene-01-start",
                    "sha256": keyframe_sha,
                    "reference_digests": [source_sha],
                    "score": 92,
                    "verdict": "pass",
                    "hard_failure": False,
                }
            ]
        },
    }
    package = {
        "schema_version": "storyboard-package-v2",
        "workflow_id": "workflow-1",
        "project_id": "project-1",
        "package_digest": "sha256:approved-package",
        "script": {"scenes": [scene]},
        "generated_keyframes": [keyframe_item],
        "keyframe_qc_receipt": receipt,
    }
    package["package_digest"] = storyboard_package_digest(package)
    receipt["artifact_digest"] = package["package_digest"]
    return project, package, source, keyframe


class _FakeRepository:
    def __init__(self, project) -> None:
        self.project = project
        self.batches = {}
        self.artifacts = {}

    def save(self, project):
        self.project = project
        return project

    def save_render_batch(self, batch):
        self.batches[batch.render_batch_id] = batch
        return batch

    def get_render_batch(self, batch_id: str):
        return self.batches.get(batch_id)

    def save_artifact(self, artifact):
        self.artifacts[artifact.artifact_id] = artifact
        return artifact

    def get_artifact(self, artifact_id: str):
        return self.artifacts.get(artifact_id)


class _FakeService:
    def __init__(self, project) -> None:
        self.repository = _FakeRepository(project)

    def get_project(self, _owner: str, _project: str):
        return self.repository.project


class _SubmitThenPollProvider:
    model = "veo-3.1-generate-001"
    provider_kind = "google_flow"

    def __init__(self) -> None:
        self.provider_kind = "google_flow"
        self.submit_calls: list[VideoGenerationRequest] = []
        self.poll_calls: list[str] = []

    def submit(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        self.submit_calls.append(request)
        return VideoGenerationResult(
            request_id=request.request_id,
            status="submitted",
            provider_operation_id="operations/video-1",
        )

    def get_status(self, operation_id: str) -> VideoGenerationResult:
        self.poll_calls.append(operation_id)
        return VideoGenerationResult(
            request_id=operation_id,
            status="running",
            provider_operation_id=operation_id,
        )


def test_server_render_checkpoints_each_scene_and_resume_polls_without_resubmit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hermes_personal.integrations.video_factory import server
    from hermes_personal.workflows.budgets import (
        BudgetPolicy,
        init_default_engine,
        reserve_budget,
    )

    project, package, source, keyframe = _render_fixture(tmp_path)
    service = _FakeService(project)
    server.set_service(service)
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "factory.sqlite"))
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_generation": 1000}))
    reservation = reserve_budget(
        "video_generation", 100, owner_user_id="operator-1", scope_id="project-1"
    )
    provider = _SubmitThenPollProvider()
    try:
        first = server.render(
            storyboard_result=package,
            owner_user_id="operator-1",
            project_id="project-1",
            admission_context={"reservation_id": reservation.reservation_id},
            provider=provider,
        )
        service.repository.project = replace(
            service.repository.project,
            draft_video_asset_id=None,
        )
        second = server.render(
            storyboard_result=package,
            owner_user_id="operator-1",
            project_id="project-1",
            admission_context={"reservation_id": reservation.reservation_id},
            provider=provider,
        )
    finally:
        server.set_service(None)

    assert first["ok"] is True
    assert second["ok"] is True
    assert len(provider.submit_calls) == 1
    assert provider.poll_calls == ["operations/video-1"]
    assert provider.submit_calls[0].reference_image_paths == (str(keyframe.resolve()),)
    assert str(source.resolve()) not in provider.submit_calls[0].reference_image_paths


def test_server_render_v2_fails_closed_without_immutable_keyframe_qc_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hermes_personal.integrations.video_factory import server
    from hermes_personal.workflows.budgets import (
        BudgetPolicy,
        init_default_engine,
        reserve_budget,
    )

    project, package, _source, _keyframe = _render_fixture(tmp_path)
    package.pop("keyframe_qc_receipt")
    server.set_service(_FakeService(project))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "factory.sqlite"))
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_generation": 1000}))
    reservation = reserve_budget(
        "video_generation", 100, owner_user_id="operator-1", scope_id="project-1"
    )
    provider = _SubmitThenPollProvider()
    try:
        result = server.render(
            storyboard_result=package,
            owner_user_id="operator-1",
            project_id="project-1",
            admission_context={"reservation_id": reservation.reservation_id},
            provider=provider,
        )
    finally:
        server.set_service(None)

    assert result["ok"] is False
    assert result["code"] == "KEYFRAME_QC_REQUIRED"
    assert provider.submit_calls == []


def test_server_render_v2_rejects_scene_mutated_after_keyframe_qc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hermes_personal.integrations.video_factory import server
    from hermes_personal.workflows.budgets import (
        BudgetPolicy,
        init_default_engine,
        reserve_budget,
    )

    project, package, _source, _keyframe = _render_fixture(tmp_path)
    package["script"]["scenes"][0]["subject_action"] = "A different unapproved action"
    server.set_service(_FakeService(project))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "factory.sqlite"))
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_generation": 1000}))
    reservation = reserve_budget(
        "video_generation", 100, owner_user_id="operator-1", scope_id="project-1"
    )
    provider = _SubmitThenPollProvider()
    try:
        result = server.render(
            storyboard_result=package,
            owner_user_id="operator-1",
            project_id="project-1",
            admission_context={"reservation_id": reservation.reservation_id},
            provider=provider,
        )
    finally:
        server.set_service(None)

    assert result["ok"] is False
    assert result["code"] == "STORYBOARD_PACKAGE_CHANGED"
    assert provider.submit_calls == []


def test_server_render_never_uses_local_listing_image_as_video_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hermes_personal.integrations.video_factory import server
    from hermes_personal.workflows.budgets import (
        BudgetPolicy,
        init_default_engine,
        reserve_budget,
    )

    project, _package, source, _keyframe = _render_fixture(tmp_path)
    server.set_service(_FakeService(project))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "factory.sqlite"))
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_generation": 1000}))
    reservation = reserve_budget(
        "video_generation", 100, owner_user_id="operator-1", scope_id="project-1"
    )
    provider = _SubmitThenPollProvider()
    try:
        result = server.render(
            storyboard_result=None,
            owner_user_id="operator-1",
            project_id="project-1",
            admission_context={"reservation_id": reservation.reservation_id},
            render_params={"reference_image_paths": [str(source)]},
            provider=provider,
        )
    finally:
        server.set_service(None)

    assert result["ok"] is False
    assert result["code"] == "KEYFRAME_PACKAGE_REQUIRED"
    assert provider.submit_calls == []
