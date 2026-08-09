from gui.tabs.prompt_studio_tab import (
    PRODUCT_FIELDS,
    STEP_DESCRIPTORS,
    url_reader_notice,
)


def test_prompt_studio_declares_the_exact_seven_steps_in_order():
    assert tuple(step.name for step in STEP_DESCRIPTORS) == (
        "Sản phẩm",
        "Phân tích",
        "Kịch bản",
        "Storyboard",
        "Prompt ảnh",
        "Prompt video",
        "Kết quả",
    )
    assert len({step.key for step in STEP_DESCRIPTORS}) == 7


def test_every_step_has_a_uniform_ai_content_descriptor():
    assert all(step.content_title for step in STEP_DESCRIPTORS)
    assert STEP_DESCRIPTORS[-1].approve_label == "Duyệt & hoàn tất"
    assert all(step.approve_label for step in STEP_DESCRIPTORS[:-1])


def test_product_step_declares_all_required_fields():
    assert tuple(field.key for field in PRODUCT_FIELDS) == (
        "product_url",
        "product_image",
        "character_image",
        "tiktok_channel",
        "video_type",
        "duration",
        "product_name",
        "short_description",
        "target_pain_points",
        "usp",
    )
    fields = {field.key: field for field in PRODUCT_FIELDS}
    assert fields["video_type"].kind == "choice"
    assert fields["duration"].kind == "choice"


def test_url_reader_notice_is_honest_about_shell_only_behavior():
    notice = url_reader_notice("https://example.com/product")

    assert "chưa kết nối" in notice.lower()
    assert "tự điền" not in notice.lower()
