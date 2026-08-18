from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Protocol, TypeVar

from hermes.domain.prompt_studio import PromptStudioStep, PromptStudioWorkflow, WorkflowStep
from hermes.domain.results import Result

T = TypeVar("T")


class WorkflowRepository(Protocol):
    def get(self, project_id: str) -> Result[PromptStudioWorkflow]:
        ...

    def save(self, workflow: PromptStudioWorkflow) -> Result[PromptStudioWorkflow]:
        ...


class PromptStudioService:
    def __init__(self, workflow_repository: WorkflowRepository):
        self.workflow_repository = workflow_repository

    def load_workflow(self, project_id: str) -> Result[PromptStudioWorkflow]:
        workflow_result = self.workflow_repository.get(project_id)
        if not workflow_result.ok:
            # If no workflow exists, initialize a new one
            if workflow_result.error_code == "not_found":
                new_workflow = PromptStudioWorkflow.initialize(project_id)
                return self.workflow_repository.save(new_workflow)
            return workflow_result
        return workflow_result

    def save_draft(self, project_id: str, step_name: PromptStudioStep, content: dict) -> Result[PromptStudioWorkflow]:
        workflow_result = self.load_workflow(project_id)
        if not workflow_result.ok:
            return workflow_result
        
        current_workflow = workflow_result.value
        updated_workflow = current_workflow.update_step_content(step_name, content)
        return self.workflow_repository.save(updated_workflow)

    def approve_step(self, project_id: str, step_name: PromptStudioStep, content: dict) -> Result[PromptStudioWorkflow]:
        workflow_result = self.load_workflow(project_id)
        if not workflow_result.ok:
            return workflow_result
        
        current_workflow = workflow_result.value
        
        # Check if previous steps are approved
        step_names = [s.name for s in current_workflow.steps]
        current_step_index = step_names.index(step_name)
        
        for i, step_in_workflow in enumerate(current_workflow.steps):
            if not step_in_workflow.approved and i < current_step_index:
                return Result.failure(
                    "conflict", 
                    f"Step '{step_name.value}' cannot be approved before '{step_in_workflow.name.value}' is approved."
                )

        updated_workflow = current_workflow.approve_step(step_name, content)
        # After approving, invalidate downstream steps if content changed? 
        # Actually, approve_step handles approving and invalidation of subsequent steps already in domain logic
        return self.workflow_repository.save(updated_workflow)

    def invalidate_from(self, project_id: str, step_name: PromptStudioStep) -> Result[PromptStudioWorkflow]:
        workflow_result = self.load_workflow(project_id)
        if not workflow_result.ok:
            return workflow_result
        
        current_workflow = workflow_result.value
        updated_workflow = current_workflow.invalidate_from(step_name)
        return self.workflow_repository.save(updated_workflow)

    def reset_workflow(self, project_id: str) -> Result[PromptStudioWorkflow]:
        new_workflow = PromptStudioWorkflow.initialize(project_id)
        return self.workflow_repository.save(new_workflow)

