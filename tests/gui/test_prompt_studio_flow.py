import pytest

from gui.prompt_studio_flow import PROMPT_STUDIO_STEPS, PromptStudioFlow


def test_flow_has_exactly_seven_ordered_steps():
    assert PROMPT_STUDIO_STEPS == (
        "Sản phẩm", "Phân tích", "Kịch bản", "Storyboard",
        "Prompt ảnh", "Prompt video", "Kết quả",
    )


def test_approving_a_step_records_content_and_advances_current_step():
    flow = PromptStudioFlow()
    next_step = flow.approve("Sản phẩm", "Thông tin sản phẩm")
    assert flow.state("Sản phẩm").content == "Thông tin sản phẩm"
    assert flow.state("Sản phẩm").approved is True
    assert next_step == "Phân tích"
    assert flow.current_step == "Phân tích"


def test_final_step_has_no_step_beyond_it():
    flow = PromptStudioFlow()
    for step in PROMPT_STUDIO_STEPS:
        next_step = flow.approve(step, f"Nội dung {step}")
    assert next_step is None
    assert flow.current_step == "Kết quả"
    assert flow.state("Kết quả").approved is True
    with pytest.raises(ValueError, match="bước cuối"):
        flow.approve("Kết quả", "Duyệt lần nữa")


@pytest.mark.parametrize("operation", ["edit", "regenerate"])
def test_changing_an_approved_step_invalidates_it_and_all_downstream(operation):
    flow = PromptStudioFlow()
    for step in PROMPT_STUDIO_STEPS[:4]:
        flow.approve(step, f"Nội dung {step}")
    getattr(flow, operation)("Phân tích", "Phân tích mới")
    assert flow.state("Sản phẩm").approved is True
    assert flow.state("Phân tích").content == "Phân tích mới"
    assert [flow.state(step).approved for step in PROMPT_STUDIO_STEPS[1:]] == [False] * 6
    assert flow.current_step == "Phân tích"


def test_step_status_exposes_current_and_approved_flags():
    flow = PromptStudioFlow()
    flow.approve("Sản phẩm", "Đã nhập")
    assert flow.status("Sản phẩm").approved is True
    assert flow.status("Sản phẩm").current is False
    assert flow.status("Phân tích").approved is False
    assert flow.status("Phân tích").current is True


def test_steps_must_be_approved_in_order():
    flow = PromptStudioFlow()
    with pytest.raises(ValueError, match="Sản phẩm"):
        flow.approve("Kịch bản", "Quá sớm")


@pytest.mark.parametrize("operation", ["edit", "regenerate"])
def test_changing_a_future_step_cannot_skip_the_current_step(operation):
    flow = PromptStudioFlow()
    with pytest.raises(ValueError, match="bước hiện tại"):
        getattr(flow, operation)("Kịch bản", "Nội dung quá sớm")
    assert flow.current_step == "Sản phẩm"
    assert flow.state("Kịch bản").content == ""
