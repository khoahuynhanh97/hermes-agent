"""Tests for Video Quality Control (Technical specs & Visual sampling QC)."""

import sqlite3
import tempfile
from fractions import Fraction
from pathlib import Path
from unittest.mock import MagicMock

import av
from PIL import Image

from hermes_personal.product_video.qc.models import (
    NormalizedProduct,
    QCStage,
    QCVerdict,
)
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.qc.video_qc import (
    check_technical_video_specs,
    run_video_qc,
)


def _create_synthetic_mp4(path: Path, width: int = 720, height: int = 1280, duration_sec: float = 1.0, fps: int = 24) -> None:
    container = av.open(str(path), mode="w")
    stream = container.add_stream("libx264", rate=fps)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    stream.time_base = Fraction(1, fps)

    num_frames = int(duration_sec * fps)
    for i in range(num_frames):
        color = ((i * 10) % 255, 128, 200)
        img = Image.new("RGB", (width, height), color=color)
        frame = av.VideoFrame.from_image(img)
        frame.time_base = Fraction(1, fps)
        frame.pts = i
        for packet in stream.encode(frame):
            container.mux(packet)

    for packet in stream.encode():
        container.mux(packet)
    container.close()


def test_video_qc_technical_check_pass():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "valid.mp4"
        _create_synthetic_mp4(video_path, width=720, height=1280, duration_sec=1.0, fps=24)

        res = check_technical_video_specs(video_path, expected_duration=1.0, duration_tolerance=0.5)
        assert res["technical_pass"] is True
        assert res["width"] == 720
        assert res["height"] == 1280
        assert res["fps"] == 24.0
        assert res["decoded_frames"] == 24
        assert res["has_audio"] is False


def test_video_qc_technical_check_fail_on_wrong_dimensions():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "wrong_dim.mp4"
        _create_synthetic_mp4(video_path, width=640, height=480, duration_sec=1.0, fps=24)

        res = check_technical_video_specs(video_path, expected_duration=1.0, duration_tolerance=0.5)
        assert res["technical_pass"] is False
        assert any("720x1280" in issue for issue in res["issues"])


def test_video_qc_visual_sampling_pass():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "composite.mp4"
        ref_path = Path(tmp) / "ref.png"
        ref_img = Image.new("RGB", (100, 100), color="blue")
        ref_img.save(ref_path)

        # 2 seconds total, 2 scenes of 1.0s each
        _create_synthetic_mp4(video_path, width=720, height=1280, duration_sec=2.0, fps=24)

        storyboard = {
            "frames": [
                    {"description": "Scene 1: Close up fan", "duration_seconds": 1.0},
                    {"description": "Scene 2: Wind blowing outdoors", "duration_seconds": 1.0},
            ]
        }
        product = NormalizedProduct(brand="Jisulife", model="Life 7", display_name="Jisulife Life 7")

        mock_evaluator = MagicMock()
        mock_evaluator.evaluator_name = "mock_vision"
        mock_evaluator.evaluator_version = "1.0"
        mock_evaluator.evaluate_multiple_images.return_value = {
            "total_score": 92,
            "identity_consistency": 47,
            "scene_adherence": 27,
            "visual_cleanliness": 18,
                "hard_failure": False,
                "source_branding_detected": False,
                "identity_mismatch": False,
                "verdict": "pass",
            "reason": "Consistent identity across scene frames",
        }

        conn = sqlite3.connect(":memory:")
        repo = QCReportRepository(conn)

        report = run_video_qc(
            workflow_id="wf-vid-1",
            video_path=video_path,
            storyboard=storyboard,
            product=product,
            approved_reference_paths=[ref_path],
            expected_duration=2.0,
            evaluator=mock_evaluator,
            repo=repo,
            owner_user_id="owner-vid-1",
            project_id="proj-vid-1",
            artifact_id="art-video-1",
            artifact_version=1,
        )

        assert report.verdict == QCVerdict.PASS
        assert report.score == 92
        assert report.stage == QCStage.VIDEO
        # 2 scenes * 5 samples = 10 sample timestamps
        assert len(report.sample_timestamps) == 10
        assert mock_evaluator.evaluate_multiple_images.call_count == 2

        # Verify saved report
        saved = repo.get_report(report.report_id)
        assert saved is not None
        assert saved.score == 92


def test_video_qc_visual_sampling_fail_on_morphing():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "composite.mp4"
        ref_path = Path(tmp) / "ref.png"
        ref_img = Image.new("RGB", (100, 100), color="blue")
        ref_img.save(ref_path)

        _create_synthetic_mp4(video_path, width=720, height=1280, duration_sec=1.0, fps=24)

        storyboard = {"frames": [{"description": "Scene 1", "duration_seconds": 1.0}]}
        product = NormalizedProduct(brand="Jisulife", model="Life 7", display_name="Jisulife Life 7")

        mock_evaluator = MagicMock()
        mock_evaluator.evaluator_name = "mock_vision"
        mock_evaluator.evaluator_version = "1.0"
        mock_evaluator.evaluate_multiple_images.return_value = {
            "total_score": 40,
            "identity_consistency": 10,
            "scene_adherence": 15,
            "visual_cleanliness": 15,
            "hard_failure": True,  # Severe morphing
            "source_branding_detected": False,
            "identity_mismatch": True,
            "verdict": "fail",
            "reason": "Product transformed into an alien teapot",
        }

        report = run_video_qc(
            workflow_id="wf-vid-fail",
            video_path=video_path,
            storyboard=storyboard,
            product=product,
            approved_reference_paths=[ref_path],
            expected_duration=1.0,
            evaluator=mock_evaluator,
            owner_user_id="owner-vid-fail",
            project_id="proj-vid-fail",
            artifact_id="art-video-fail",
            artifact_version=1,
        )

        assert report.verdict == QCVerdict.FAIL
        assert report.score < 80


def test_video_qc_prompt_rejects_source_store_branding():
    from hermes_personal.product_video.qc.rubric import (
        VIDEO_QC_SYSTEM_PROMPT,
        build_video_sampling_qc_prompt,
    )

    prompt = build_video_sampling_qc_prompt(
        scene_number=1,
        scene_intent="Clean product close-up",
        brand="AULA",
        model="F75",
        sample_timestamps=[0.15, 0.5, 0.85],
    ).lower()
    system_prompt = VIDEO_QC_SYSTEM_PROMPT.lower()

    assert "seller/shop/source branding" in system_prompt
    assert "watermarks" in system_prompt
    assert "marketplace ui" in prompt
    assert "hard_failure" in prompt


def test_video_qc_allows_only_verified_flow_native_mark():
    from hermes_personal.product_video.qc.rubric import build_video_sampling_qc_prompt

    common = dict(
        scene_number=1, scene_intent="Pick up speaker", brand="Tribit",
        model="XSound Go", sample_timestamps=[0.2, 1.0, 2.0, 3.0, 3.8],
    )
    flow_prompt = build_video_sampling_qc_prompt(**common, provider_kind="google_flow")
    vertex_prompt = build_video_sampling_qc_prompt(**common, provider_kind="vertex_ai")

    assert "Verified scene provider: Google Flow" in flow_prompt
    assert "native watermark, including the sparkle mark, is allowed" in flow_prompt
    assert "all third-party watermarks" in flow_prompt
    assert "No provider watermark exception" in vertex_prompt


def test_flow_native_mark_exception_requires_verified_provider_and_no_other_failure():
    from hermes_personal.product_video.qc.video_qc import _allow_verified_flow_native_mark

    evaluation = {
        "total_score": 80,
        "verdict": "fail",
        "hard_failure": True,
        "source_branding_detected": True,
        "native_flow_watermark_only": True,
        "identity_mismatch": False,
        "interaction_geometry_valid": True,
        "product_count_valid": True,
    }
    assert _allow_verified_flow_native_mark(evaluation, "vertex_ai") is evaluation
    assert _allow_verified_flow_native_mark(
        {**evaluation, "native_flow_watermark_only": False}, "google_flow"
    )["hard_failure"] is True
    allowed = _allow_verified_flow_native_mark(evaluation, "google_flow")
    assert allowed["verdict"] == "pass"
    assert allowed["source_branding_detected"] is False
    assert _allow_verified_flow_native_mark(
        {**evaluation, "identity_mismatch": True}, "google_flow"
    )["hard_failure"] is True


def test_video_qc_samples_use_approved_scene_durations():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "composite.mp4"
        ref_path = Path(tmp) / "ref.png"
        Image.new("RGB", (100, 100), color="blue").save(ref_path)
        _create_synthetic_mp4(video_path, width=720, height=1280, duration_sec=3.0, fps=24)

        evaluator = MagicMock()
        evaluator.evaluator_name = "mock_vision"
        evaluator.evaluator_version = "1.0"
        evaluator.evaluate_multiple_images.return_value = {
            "total_score": 90,
            "identity_consistency": 45,
            "scene_adherence": 27,
            "visual_cleanliness": 18,
            "hard_failure": False,
            "verdict": "pass",
            "reason": "ok",
        }

        report = run_video_qc(
            workflow_id="wf-boundaries",
            video_path=video_path,
            storyboard={
                "frames": [
                    {"description": "Hook", "duration_seconds": 1.0},
                    {"description": "Demo", "duration_seconds": 2.0},
                ]
            },
            product=NormalizedProduct(brand="AULA", model="F75", display_name="AULA F75"),
            approved_reference_paths=[ref_path],
            expected_duration=3.0,
            evaluator=evaluator,
            owner_user_id="owner-boundaries",
            project_id="proj-boundaries",
            artifact_id="art-video-boundaries",
            artifact_version=1,
        )

        assert report.findings["sample_coverage"]["total_scenes_evaluated"] == 2
        assert report.sample_timestamps == [0.05, 0.25, 0.5, 0.75, 0.95, 1.1, 1.5, 2.0, 2.5, 2.9]


def test_video_qc_branding_flag_blocks_high_score_scene():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "composite.mp4"
        ref_path = Path(tmp) / "ref.png"
        Image.new("RGB", (100, 100), color="blue").save(ref_path)
        _create_synthetic_mp4(video_path, width=720, height=1280, duration_sec=1.0, fps=24)

        evaluator = MagicMock()
        evaluator.evaluator_name = "mock_vision"
        evaluator.evaluator_version = "1.0"
        evaluator.evaluate_multiple_images.return_value = {
            "total_score": 95,
            "identity_consistency": 50,
            "scene_adherence": 30,
            "visual_cleanliness": 15,
            "hard_failure": False,
            "source_branding_detected": True,
            "identity_mismatch": False,
            "verdict": "pass",
            "reason": "Minh Gear watermark visible",
        }

        report = run_video_qc(
            workflow_id="wf-video-branding",
            video_path=video_path,
            storyboard={"frames": [{"description": "Clean close-up", "duration_seconds": 1.0}]},
            product=NormalizedProduct(brand="AULA", model="F75", display_name="AULA F75"),
            approved_reference_paths=[ref_path],
            expected_duration=1.0,
            evaluator=evaluator,
            owner_user_id="owner-branding",
            project_id="proj-branding",
            artifact_id="art-video-branding",
            artifact_version=1,
        )

        assert report.verdict == QCVerdict.FAIL
        assert report.findings["visual_scenes"][0]["hard_failure"] is True


def test_video_qc_black_bar_allegation_disagrees_with_measured_video():
    with tempfile.TemporaryDirectory() as tmp:
        video_path = Path(tmp) / "composite.mp4"
        ref_path = Path(tmp) / "ref.png"
        Image.new("RGB", (100, 100), color="blue").save(ref_path)
        _create_synthetic_mp4(video_path, width=720, height=1280, duration_sec=1.0, fps=24)

        evaluator = MagicMock()
        evaluator.evaluator_name = "mock_vision"
        evaluator.evaluator_version = "1.0"
        evaluator.evaluate_multiple_images.return_value = {
            "total_score": 90,
            "identity_consistency": 45,
            "scene_adherence": 27,
            "visual_cleanliness": 18,
            "hard_failure": True,
            "verdict": "fail",
            "reason": "Persistent black bars at the top and bottom",
        }

        report = run_video_qc(
            workflow_id="wf-video-black-bar-conflict",
            video_path=video_path,
            storyboard={"frames": [{"description": "Product close-up", "duration_seconds": 1.0}]},
            product=NormalizedProduct(brand="AULA", model="F75", display_name="AULA F75"),
            approved_reference_paths=[ref_path],
            expected_duration=1.0,
            evaluator=evaluator,
            owner_user_id="owner-conflict",
            project_id="proj-conflict",
            artifact_id="art-video-conflict",
            artifact_version=1,
        )

        assert report.findings["technical_specs"]["black_bars"]["has_persistent_black_bars"] is False
        assert report.verdict == QCVerdict.UNKNOWN
        assert report.findings["recovery_actions"] == ["manual_review_technical_conflict"]
