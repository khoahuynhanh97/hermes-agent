"""GUI-independent state for Prompt Studio's sequential workflow."""

from dataclasses import dataclass, replace
from typing import Optional


PROMPT_STUDIO_STEPS = (
    "Sản phẩm",
    "Phân tích",
    "Kịch bản",
    "Storyboard",
    "Prompt ảnh",
    "Prompt video",
    "Kết quả",
)


@dataclass(frozen=True)
class StepState:
    content: str = ""
    approved: bool = False


@dataclass(frozen=True)
class StepStatus:
    current: bool
    approved: bool


class PromptStudioFlow:
    def __init__(self) -> None:
        self._states = {step: StepState() for step in PROMPT_STUDIO_STEPS}
        self._current_index = 0

    @property
    def current_step(self) -> str:
        return PROMPT_STUDIO_STEPS[self._current_index]

    def reset(self) -> None:
        """Discard all step content and approvals and return to the first step."""
        self._states = {step: StepState() for step in PROMPT_STUDIO_STEPS}
        self._current_index = 0

    def state(self, step: str) -> StepState:
        self._validate_step(step)
        return self._states[step]

    def status(self, step: str) -> StepStatus:
        state = self.state(step)
        return StepStatus(current=step == self.current_step, approved=state.approved)

    def approve(self, step: str, content: str) -> Optional[str]:
        self._validate_step(step)
        if step != self.current_step:
            raise ValueError(f"Cần duyệt bước {self.current_step} trước")
        if self._states[step].approved:
            raise ValueError("Không thể duyệt vượt quá bước cuối")

        self._states[step] = StepState(content=content, approved=True)
        if self._current_index == len(PROMPT_STUDIO_STEPS) - 1:
            return None

        self._current_index += 1
        return self.current_step

    def edit(self, step: str, content: str) -> None:
        self._change(step, content)

    def regenerate(self, step: str, content: str) -> None:
        self._change(step, content)

    def _change(self, step: str, content: str) -> None:
        self._validate_step(step)
        changed_index = PROMPT_STUDIO_STEPS.index(step)
        if changed_index > self._current_index:
            raise ValueError(
                f"Không thể thay đổi bước tương lai trước bước hiện tại: "
                f"{self.current_step}"
            )
        self._states[step] = replace(self._states[step], content=content)
        for downstream_step in PROMPT_STUDIO_STEPS[changed_index:]:
            self._states[downstream_step] = replace(
                self._states[downstream_step], approved=False
            )
        self._current_index = changed_index

    @staticmethod
    def _validate_step(step: str) -> None:
        if step not in PROMPT_STUDIO_STEPS:
            raise ValueError(f"Bước Prompt Studio không hợp lệ: {step}")
