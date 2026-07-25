from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.dependencies import get_job_service

router = APIRouter()


class JobSubmitRequest(BaseModel):
    task_name: str
    payload: dict | None = None


class JobResponse(BaseModel):
    id: str
    task_name: str
    status: str


@router.post("", response_model=JobResponse, status_code=201)
def submit_job(body: JobSubmitRequest, service=Depends(get_job_service)):
    job_id = service.submit_job(body.task_name, body.payload or {})
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Job was not created")
    return JobResponse(id=job.id, task_name=job.task_name, status=job.status.name)


@router.get("/{job_id}")
def get_job(job_id: str, service=Depends(get_job_service)):
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(id=job.id, task_name=job.task_name, status=job.status.name)