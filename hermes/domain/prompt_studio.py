from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PromptStudioStep(str, Enum):
    PRODUCT = "product"
    ANALYSIS = "analysis"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    IMAGE_PROMPT = "image_prompt"
    VIDEO_PROMPT = "video_prompt"
    RESULT = "result"


@dataclass(frozen=True)
class WorkflowStep:
    name: PromptStudioStep
    content: dict = field(default_factory=dict)
    approved: bool = False
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass(frozen=True)
class PromptStudioWorkflow:
    project_id: str
    steps: list[WorkflowStep]

    @staticmethod
    def initialize(project_id: str) -> "PromptStudioWorkflow":
        return PromptStudioWorkflow(
            project_id=project_id,
            steps=[
                WorkflowStep(PromptStudioStep.PRODUCT),
                WorkflowStep(PromptStudioStep.ANALYSIS),
                WorkflowStep(PromptStudioStep.SCRIPT),
                WorkflowStep(PromptStudioStep.STORYBOARD),
                WorkflowStep(PromptStudioStep.IMAGE_PROMPT),
                WorkflowStep(PromptStudioStep.VIDEO_PROMPT),
                WorkflowStep(PromptStudioStep.RESULT),
            ],
        )

    def get_step(self, step_name: PromptStudioStep) -> WorkflowStep | None:
        for step in self.steps:
            if step.name == step_name:
                return step
        return None

    def update_step_content(self, step_name: PromptStudioStep, content: dict) -> "PromptStudioWorkflow":
        updated_steps = []
        found = False
        invalidate_from_here = False
        # Find the index of the step being updated to invalidate subsequent steps
        try:
            current_step_index = [s.name for s in self.steps].index(step_name)
        except ValueError:
            raise ValueError(f"Step {step_name} not found in workflow.")


        for i, step in enumerate(self.steps):
            if step.name == step_name:
                updated_steps.append(WorkflowStep(
                    name=step.name,
                    content=content,
                    approved=False,  # Content change invalidates approval
                    updated_at=datetime.now().isoformat(),
                ))
                invalidate_from_here = True # Start invalidating from this step onwards
                found = True
            elif invalidate_from_here:
                updated_steps.append(WorkflowStep(
                    name=step.name,
                    content={},
                    approved=False,
                    updated_at=datetime.now().isoformat(),
                ))
            else:
                updated_steps.append(step)
        if not found:
            raise ValueError(f"Step {step_name} not found in workflow.")
        return PromptStudioWorkflow(project_id=self.project_id, steps=updated_steps)

    def approve_step(self, step_name: PromptStudioStep, content: dict) -> "PromptStudioWorkflow":
        updated_steps = []
        invalidate_from_here = False
        # Get the index of the current step being approved
        try:
            current_step_index = [s.name for s in self.steps].index(step_name)
        except ValueError:
            raise ValueError(f"Step {step_name} not found in workflow.")

        for i, step in enumerate(self.steps):
            if step.name == step_name:
                updated_steps.append(WorkflowStep(
                    name=step.name,
                    content=content,
                    approved=True,
                    updated_at=datetime.now().isoformat(),
                ))
                invalidate_from_here = True
            elif invalidate_from_here: # Invalidate all subsequent steps after the approved one
                updated_steps.append(WorkflowStep(
                    name=step.name,
                    content={},
                    approved=False,
                    updated_at=datetime.now().isoformat(),
                ))
            else:
                updated_steps.append(step)
        
        return PromptStudioWorkflow(project_id=self.project_id, steps=updated_steps)

    def invalidate_from(self, step_name: PromptStudioStep) -> "PromptStudioWorkflow":
        updated_steps = []
        invalidate_flag = False
        for step in self.steps:
            if step.name == step_name:
                invalidate_flag = True
            
            if invalidate_flag:
                updated_steps.append(WorkflowStep(
                    name=step.name,
                    content={},
                    approved=False,
                    updated_at=datetime.now().isoformat(),
                ))
            else:
                updated_steps.append(step)
        return PromptStudioWorkflow(project_id=self.project_id, steps=updated_steps)
