from __future__ import annotations

import pytest
from hermes.application.prompt_studio_service import PromptStudioService
from hermes.domain.prompt_studio import PromptStudioStep, PromptStudioWorkflow, WorkflowStep
from hermes.domain.results import Result
from hermes.ports.workflow_repository import WorkflowRepository
from datetime import datetime


class InMemoryWorkflowRepository(WorkflowRepository):
    def __init__(self):
        self._workflows: dict[str, PromptStudioWorkflow] = {}

    def get(self, project_id: str) -> Result[PromptStudioWorkflow]:
        workflow = self._workflows.get(project_id)
        if workflow:
            return Result.success(workflow)
        return Result.failure("not_found", f"Workflow for project {project_id} not found.")

    def save(self, workflow: PromptStudioWorkflow) -> Result[PromptStudioWorkflow]:
        self._workflows[workflow.project_id] = workflow
        return Result.success(workflow)


@pytest.fixture
def workflow_repository():
    return InMemoryWorkflowRepository()


@pytest.fixture
def service(workflow_repository):
    return PromptStudioService(workflow_repository)


@pytest.fixture
def project_id():
    return "test-project-123"


@pytest.fixture
def workflow(project_id):
    wf = PromptStudioWorkflow.initialize(project_id)
    # Manually set some steps as approved for testing sequential approval
    steps = list(wf.steps)
    steps[0] = WorkflowStep(PromptStudioStep.PRODUCT, {"name": "Product Idea"}, approved=True, updated_at=datetime.now().isoformat())
    steps[1] = WorkflowStep(PromptStudioStep.ANALYSIS, {"angle": "Market"}, approved=True, updated_at=datetime.now().isoformat())
    return PromptStudioWorkflow(project_id, steps)


def test_approving_script_invalidates_storyboard_and_later_steps(service, project_id):
    # Initialize workflow and approve first two steps
    service.approve_step(project_id, PromptStudioStep.PRODUCT, {"name": "Stand"})
    service.approve_step(project_id, PromptStudioStep.ANALYSIS, {"angle": "demo"})

    # Approve script and storyboard
    service.approve_step(project_id, PromptStudioStep.SCRIPT, {"text": "v1"})
    service.approve_step(project_id, PromptStudioStep.STORYBOARD, {"scenes": [1]})

    # Now, save a draft to script, which should invalidate downstream steps
    service.save_draft(project_id, PromptStudioStep.SCRIPT, {"text": "v2"})
    
    state = service.load_workflow(project_id).value
    assert state is not None
    assert state.get_step(PromptStudioStep.STORYBOARD).approved is False
    assert state.get_step(PromptStudioStep.IMAGE_PROMPT).approved is False


def test_initial_workflow_is_created_if_not_found(service, project_id):
    result = service.load_workflow(project_id)
    assert result.ok
    assert result.value is not None
    assert result.value.project_id == project_id
    assert len(result.value.steps) == 7
    assert all(not step.approved for step in result.value.steps)


def test_save_draft_updates_content_and_invalidates_approval(service, project_id):
    service.load_workflow(project_id) # Ensure workflow exists
    service.approve_step(project_id, PromptStudioStep.PRODUCT, {"name": "Old Name"})
    
    result = service.save_draft(project_id, PromptStudioStep.PRODUCT, {"name": "New Name"})
    assert result.ok
    assert result.value.get_step(PromptStudioStep.PRODUCT).content == {"name": "New Name"}
    assert not result.value.get_step(PromptStudioStep.PRODUCT).approved


def test_approve_step_sets_approved_and_content(service, project_id):
    service.load_workflow(project_id)
    service.approve_step(project_id, PromptStudioStep.PRODUCT, {"name": "Approved Product"})
    service.approve_step(project_id, PromptStudioStep.ANALYSIS, {"type": "Approved Analysis"})

    workflow = service.load_workflow(project_id).value
    assert workflow.get_step(PromptStudioStep.PRODUCT).approved
    assert workflow.get_step(PromptStudioStep.PRODUCT).content == {"name": "Approved Product"}
    assert workflow.get_step(PromptStudioStep.ANALYSIS).approved
    assert workflow.get_step(PromptStudioStep.ANALYSIS).content == {"type": "Approved Analysis"}


def test_approve_step_requires_sequential_approval(service, project_id):
    service.load_workflow(project_id)
    # Try to approve SCRIPT before PRODUCT and ANALYSIS
    result = service.approve_step(project_id, PromptStudioStep.SCRIPT, {"text": "script"})
    assert not result.ok
    assert result.error_code == "conflict"
    assert f"Step '{PromptStudioStep.SCRIPT.value}' cannot be approved before '{PromptStudioStep.PRODUCT.value}' is approved." in result.message


def test_invalidate_from_clears_downstream_steps(service, project_id):
    # Setup: Approve product, analysis, script, storyboard
    service.approve_step(project_id, PromptStudioStep.PRODUCT, {"name": "Stand"})
    service.approve_step(project_id, PromptStudioStep.ANALYSIS, {"angle": "demo"})
    service.approve_step(project_id, PromptStudioStep.SCRIPT, {"text": "v1"})
    service.approve_step(project_id, PromptStudioStep.STORYBOARD, {"scenes": [1]})

    # Invalidate from ANALYSIS
    result = service.invalidate_from(project_id, PromptStudioStep.ANALYSIS)
    assert result.ok
    workflow = result.value

    # PRODUCT should still be approved
    assert workflow.get_step(PromptStudioStep.PRODUCT).approved
    # ANALYSIS and all subsequent steps should be invalidated
    assert not workflow.get_step(PromptStudioStep.ANALYSIS).approved
    assert not workflow.get_step(PromptStudioStep.SCRIPT).approved
    assert not workflow.get_step(PromptStudioStep.STORYBOARD).approved
    assert not workflow.get_step(PromptStudioStep.IMAGE_PROMPT).approved


def test_reset_workflow_reinitializes_all_steps(service, project_id):
    # Setup: Approve some steps and save drafts
    service.approve_step(project_id, PromptStudioStep.PRODUCT, {"name": "Old Product"})
    service.save_draft(project_id, PromptStudioStep.SCRIPT, {"text": "Draft Script"})

    result = service.reset_workflow(project_id)
    assert result.ok
    workflow = result.value

    assert all(not step.approved for step in workflow.steps)
    assert all(not step.content for step in workflow.steps)
