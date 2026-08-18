from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hermes.channels.api.dependencies import get_prompt_studio_service

router = APIRouter(prefix="/prompt-studio")


class SaveDraftRequest(BaseModel):
    step: str
    content: dict


class ApproveRequest(BaseModel):
    step: str
    content: dict


def _default_content(project_id: str, step_name: str) -> dict:
    return {}


@router.get("/{project_id}")
def load_project(project_id: str, service=Depends(get_prompt_studio_service)):
    result = service.load_workflow(project_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error_code)
    workflow = result.value
    steps_data = []
    for s in workflow.steps:
        step_str = s.name.value if hasattr(s.name, "value") else str(s.name)
        content = s.content if s.content else _default_content(project_id, step_str)
        steps_data.append({
            "name": step_str,
            "content": content,
            "approved": s.approved,
            "updated_at": s.updated_at,
        })
    return {"project_id": project_id, "steps": steps_data}


@router.post("/{project_id}/draft")
def save_draft(project_id: str, body: SaveDraftRequest, service=Depends(get_prompt_studio_service)):
    from hermes.domain.prompt_studio import PromptStudioStep
    step_name = PromptStudioStep(body.step)
    result = service.save_draft(project_id, step_name, body.content)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error_code)
    return {"ok": True}


@router.post("/{project_id}/approve")
def approve_step(project_id: str, body: ApproveRequest, service=Depends(get_prompt_studio_service)):
    from hermes.domain.prompt_studio import PromptStudioStep
    step_name = PromptStudioStep(body.step)
    result = service.approve_step(project_id, step_name, body.content)
    if not result.ok:
        raise HTTPException(status_code=409, detail=result.error_code)
    return {"ok": True}


@router.post("/{project_id}/invalidate")
def invalidate_from(project_id: str, body: SaveDraftRequest, service=Depends(get_prompt_studio_service)):
    from hermes.domain.prompt_studio import PromptStudioStep
    step_name = PromptStudioStep(body.step)
    result = service.invalidate_from(project_id, step_name)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error_code)
    return {"ok": True}