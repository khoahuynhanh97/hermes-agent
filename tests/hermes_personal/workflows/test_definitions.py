import pytest
from hermes_personal.workflows.definitions import DEFINITIONS
from hermes_personal.workflows.models import IllegalTransition

def test_definitions_exist():
    expected = [
        "product_to_video",
        "product_research",
        "knowledge_learning",
        "hook_cta_learning",
        "video_deconstruction",
    ]
    for name in expected:
        assert name in DEFINITIONS
        assert DEFINITIONS[name].name == name

def test_product_to_video_transitions():
    wf = DEFINITIONS["product_to_video"]
    # Test legal transition
    wf.validate_transition("idle", "product_research")
    wf.validate_transition("product_research", "resource_pack_building")

    # Test illegal transition (rejection)
    with pytest.raises(IllegalTransition) as excinfo:
        wf.validate_transition("idle", "script_generation")
    assert "Transition not allowed" in str(excinfo.value)

    with pytest.raises(IllegalTransition) as excinfo:
        wf.validate_transition("idle", "non_existent_state")
    assert "Target state not in state machine" in str(excinfo.value)

def test_required_artifacts():
    wf = DEFINITIONS["product_to_video"]
    assert "product_research_report" in wf.required_artifacts["resource_pack_building"]
    assert "resource_pack" in wf.required_artifacts["script_generation"]

def test_approval_requirements():
    wf = DEFINITIONS["product_to_video"]
    assert wf.approval_required.get("script_generation") is True
    assert wf.approval_required.get("video_production") is True
    assert wf.approval_required.get("idle") is not True

def test_video_deconstruction_parallel_start():
    wf = DEFINITIONS["video_deconstruction"]
    wf.validate_transition("idle", "extracting_frames")
    wf.validate_transition("idle", "analyzing_audio")
