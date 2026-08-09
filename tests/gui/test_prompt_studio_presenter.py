from gui.prompt_studio_flow import PROMPT_STUDIO_STEPS, PromptStudioFlow
from gui.tabs.prompt_studio_tab import PromptStudioPresenter


class FakeView:
    def __init__(self):
        self.content = {step: f"live:{step}" for step in PROMPT_STUDIO_STEPS}
        self.editable = {}
        self.selected = None
        self.status_refreshes = 0
        self.reset_calls = 0

    def get_content(self, step):
        return self.content[step]

    def set_editable(self, step, editable):
        self.editable[step] = editable

    def select_step(self, step):
        self.selected = step

    def refresh_statuses(self):
        self.status_refreshes += 1

    def reset_content(self):
        self.reset_calls += 1
        self.content = {step: "" for step in PROMPT_STUDIO_STEPS}


def make_presenter():
    view = FakeView()
    presenter = PromptStudioPresenter(
        PromptStudioFlow(),
        view.get_content,
        view.set_editable,
        view.select_step,
        view.refresh_statuses,
        view.reset_content,
    )
    return presenter, view


def test_initial_state_only_unlocks_the_current_product_step():
    presenter, view = make_presenter()

    presenter.sync_view()

    assert view.editable["Sản phẩm"] is True
    assert all(view.editable[step] is False for step in PROMPT_STUDIO_STEPS[1:])


def test_approve_locks_step_unlocks_next_and_advances_view():
    presenter, view = make_presenter()

    next_step = presenter.approve("Sản phẩm")

    assert next_step == "Phân tích"
    assert presenter.flow.state("Sản phẩm").content == "live:Sản phẩm"
    assert presenter.flow.state("Sản phẩm").approved is True
    assert view.editable["Sản phẩm"] is False
    assert view.editable["Phân tích"] is True
    assert view.selected == "Phân tích"
    assert view.status_refreshes == 1


def test_edit_invalidates_approved_step_unlocks_it_and_returns_to_it():
    presenter, view = make_presenter()
    presenter.approve("Sản phẩm")
    presenter.approve("Phân tích")

    presenter.edit("Sản phẩm")

    assert presenter.flow.state("Sản phẩm").approved is False
    assert presenter.flow.state("Phân tích").approved is False
    assert presenter.flow.current_step == "Sản phẩm"
    assert view.editable["Sản phẩm"] is True
    assert view.editable["Phân tích"] is False
    assert view.selected == "Sản phẩm"


def test_copy_uses_approved_snapshot_instead_of_unapproved_live_value():
    presenter, view = make_presenter()
    presenter.approve("Sản phẩm")
    view.content["Sản phẩm"] = "mutated live value"

    assert presenter.content_to_copy("Sản phẩm") == "live:Sản phẩm"


def test_reset_discards_an_advanced_project_and_restores_clean_step_one():
    presenter, view = make_presenter()
    presenter.approve("Sản phẩm")
    presenter.approve("Phân tích")

    presenter.reset()

    assert presenter.flow.current_step == "Sản phẩm"
    assert all(not presenter.flow.state(step).approved for step in PROMPT_STUDIO_STEPS)
    assert all(presenter.flow.state(step).content == "" for step in PROMPT_STUDIO_STEPS)
    assert view.reset_calls == 1
    assert view.editable["Sản phẩm"] is True
    assert all(view.editable[step] is False for step in PROMPT_STUDIO_STEPS[1:])
    assert view.selected == "Sản phẩm"
