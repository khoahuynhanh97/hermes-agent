from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hermes.channels.api.dependencies import get_project_repository

router = APIRouter()


class ProjectCreateRequest(BaseModel):
    name: str


class ProjectResponse(BaseModel):
    id: str
    name: str


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreateRequest, repo=Depends(get_project_repository)):
    from hermes.domain.results import Result
    result = repo.create(body.name)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.message or result.error_code)
    project = result.value
    return ProjectResponse(id=project.id, name=project.name)


@router.get("")
def list_projects(repo=Depends(get_project_repository)):
    from hermes.domain.results import Result
    result = repo.list_active()
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.message or result.error_code)
    return [ProjectResponse(id=p.id, name=p.name) for p in result.value]


@router.get("/{project_id}")
def get_project(project_id: str, repo=Depends(get_project_repository)):
    from hermes.domain.results import Result
    result = repo.get(project_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error_code)
    project = result.value
    return ProjectResponse(id=project.id, name=project.name)


@router.delete("/{project_id}")
def archive_project(project_id: str, repo=Depends(get_project_repository)):
    from hermes.domain.results import Result
    result = repo.archive(project_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error_code)
    return {"ok": True}