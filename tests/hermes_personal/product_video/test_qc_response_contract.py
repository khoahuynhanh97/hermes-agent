import pytest

from hermes_personal.product_video.qc.evaluator import validate_qc_response
from hermes_personal.product_video.qc.models import QCStage


@pytest.mark.parametrize("bad", [
    {"total_score": 95, "verdict": "pass"},
    {"total_score": 95, "verdict": "pass", "hard_failure": "false"},
])
def test_incomplete_response_never_becomes_pass(bad):
    with pytest.raises(ValueError):
        validate_qc_response(bad, QCStage.IMAGE)


def test_image_response_with_source_branding_is_normalized_as_hard_failure():
    result = validate_qc_response(
        {
            "identity_score": 60,
            "clarity_score": 25,
            "usability_score": 15,
            "total_score": 100,
            "verdict": "pass",
            "eligible": True,
            "hard_failure": False,
            "source_branding_detected": True,
            "identity_mismatch": False,
            "view_angle": "front",
            "shot_type": "clean product",
            "visible_details": ["product body"],
            "scene_suitability": ["hero"],
            "risk_flags": ["watermark"],
            "text_coverage_percent": 5,
            "reason": "Seller watermark visible",
        },
        QCStage.IMAGE,
    )

    assert result["source_branding_detected"] is True
    assert result["hard_failure"] is True


def test_image_response_missing_reference_profile_fails_closed():
    with pytest.raises(ValueError, match="view_angle"):
        validate_qc_response(
            {
                "identity_score": 55,
                "clarity_score": 23,
                "usability_score": 12,
                "total_score": 90,
                "verdict": "pass",
                "eligible": True,
                "hard_failure": False,
                "source_branding_detected": False,
                "identity_mismatch": False,
                "reason": "Looks clean but profile is incomplete",
            },
            QCStage.IMAGE,
        )


def test_keyframe_response_missing_fidelity_gates_fails_closed():
    with pytest.raises(ValueError, match="prompt_reference_consistent"):
        validate_qc_response(
            {
                "identity_consistency": 45,
                "scene_adherence": 27,
                "visual_cleanliness": 18,
                "total_score": 90,
                "verdict": "pass",
                "hard_failure": False,
                "source_branding_detected": False,
                "identity_mismatch": False,
                "reason": "Incomplete keyframe assessment",
            },
            QCStage.KEYFRAME,
        )


def test_video_response_rejects_component_sum_mismatch():
    with pytest.raises(ValueError):
        validate_qc_response(
            {
                "identity_consistency": 45,
                "scene_adherence": 25,
                "visual_cleanliness": 20,
                "total_score": 95,
                "verdict": "pass",
                "hard_failure": False,
                "source_branding_detected": False,
                "identity_mismatch": False,
                "reason": "ok",
            },
            QCStage.VIDEO,
        )
