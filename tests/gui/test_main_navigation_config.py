from pathlib import Path


APP_SOURCE = Path(__file__).parents[2] / "gui" / "app.py"
IDEA_ENGINE_SOURCE = Path(__file__).parents[2] / "gui" / "tabs" / "idea_engine_tab.py"


def test_main_navigation_declares_exactly_three_modules_in_model_one_order():
    from gui.app import MAIN_MODULES

    assert tuple(module.label for module in MAIN_MODULES) == (
        "Prompt Studio",
        "Cắt Ghép Video",
        "Học & Duyệt kiến thức AI",
    )
    assert MAIN_MODULES[0].is_default is True
    assert sum(module.is_default for module in MAIN_MODULES) == 1


def test_topbar_utilities_keep_secondary_features_accessible():
    from gui.app import TOPBAR_UTILITIES

    assert tuple(item.label for item in TOPBAR_UTILITIES) == (
        "Quy trình tự động",
        "Kiểm tra hệ thống",
        "Công việc AI",
        "Assistant",
        "Cài đặt",
    )


def test_root_layout_does_not_create_or_reserve_a_fixed_sidebar():
    source = APP_SOURCE.read_text(encoding="utf-8")
    init_source = source.split("def create_sidebar", 1)[0]

    assert "self.create_sidebar()" not in init_source
    assert "minsize=240" not in init_source
    assert "self.workspace_frame.grid(row=0, column=0" in source


def test_semantic_routes_resolve_primary_and_utility_destinations():
    from gui.app import resolve_module_destination, resolve_utility_destination

    assert resolve_module_destination("prompt_studio") == ("prompt_studio", None)
    assert resolve_module_destination("video_editor") == ("video_editor", None)
    assert resolve_module_destination("knowledge_review") == (
        "knowledge_review",
        "📚 Học & Duyệt",
    )
    assert resolve_utility_destination("agent_jobs") == (
        "knowledge_review",
        "⚙️ Công Việc AI",
    )
    assert resolve_utility_destination("assistant") == (
        "knowledge_review",
        "Assistant",
    )
    assert resolve_utility_destination("settings") == (
        "knowledge_review",
        "🛠️ Cài Đặt",
    )


def test_auto_pipeline_completion_routes_to_visible_video_editor_tab():
    from gui.app import AUTO_PIPELINE_DESTINATION

    assert AUTO_PIPELINE_DESTINATION == ("video_editor", "🎬 Dựng video")


def test_topbar_fixed_width_budget_fits_declared_minimum_with_margin():
    from gui.app import TOPBAR_LAYOUT

    assert TOPBAR_LAYOUT.minimum_window_width == 1200
    assert TOPBAR_LAYOUT.required_width <= (
        TOPBAR_LAYOUT.minimum_window_width - TOPBAR_LAYOUT.outer_margin
    )
    assert TOPBAR_LAYOUT.remaining_width >= 100


def test_auto_pipeline_source_uses_semantic_destination_not_prompt_flow():
    source = APP_SOURCE.read_text(encoding="utf-8")
    finish_source = source.split("def finish_run", 1)[1].split(
        "btn_run.configure(command", 1
    )[0]

    assert "AUTO_PIPELINE_DESTINATION" in finish_source
    assert "switch_flow(1)" not in finish_source


def test_idea_engine_storyboard_button_uses_visible_semantic_route():
    source = IDEA_ENGINE_SOURCE.read_text(encoding="utf-8")

    assert 'show_module("knowledge_review", "🖼️ Storyboard")' in source
    assert "switch_flow(" not in source
    assert "tab_flow2.set" not in source


def test_project_creation_preserves_current_module_and_resets_prompt_step_only():
    from gui.app import destination_after_project_creation

    assert destination_after_project_creation("prompt_studio") == (
        "prompt_studio",
        0,
    )
    assert destination_after_project_creation("video_editor") == (
        "video_editor",
        None,
    )
    assert destination_after_project_creation("knowledge_review") == (
        "knowledge_review",
        None,
    )


def test_system_check_report_aggregates_all_three_results():
    from gui.app import format_system_check_report

    report = format_system_check_report(
        {"FFmpeg": True, "Gemini API": False, "yt-dlp": True}
    )

    assert "FFmpeg: Sẵn sàng" in report
    assert "Gemini API: Cần kiểm tra" in report
    assert "yt-dlp: Sẵn sàng" in report
    assert "2/3 thành phần sẵn sàng" in report


def test_system_check_action_shows_one_aggregate_dialog():
    source = APP_SOURCE.read_text(encoding="utf-8")
    check_source = source.split("def _run_all_checks", 1)[1].split(
        "def check_ffmpeg", 1
    )[0]

    assert "format_system_check_report" in check_source
    assert "messagebox.showinfo" in check_source
    assert "check_gemini(show_dialog=False)" in check_source
