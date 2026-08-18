from __future__ import annotations

from typing import Any

from hermes.domain.results import Result
from hermes.ports.job_repository import JobRepository
from hermes.domain.job import JobStatus


class VideoService:
    def __init__(self, job_repository: JobRepository):
        self.job_repository = job_repository

    def request_cut(self, asset_id: str, start_seconds: int, end_seconds: int, *, owner_user_id: str = "system", output_path: str = "") -> Result[Job]:
        from hermes.domain.job import Job
        payload = {
            "asset_id": asset_id,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "owner_user_id": owner_user_id,
        }
        if output_path:
            payload["output_path"] = output_path
        job = Job.new("video.cut", payload)
        self.job_repository.submit(job)
        return Result.success(job)

    def request_render(self, asset_id: str, output_format: str = "mp4", *, owner_user_id: str = "system", output_path: str = "") -> Result[Job]:
        from hermes.domain.job import Job
        payload = {
            "asset_id": asset_id,
            "output_format": output_format,
            "owner_user_id": owner_user_id,
        }
        if output_path:
            payload["output_path"] = output_path
        job = Job.new("video.render", payload)
        self.job_repository.submit(job)
        return Result.success(job)

    def get_jobs_by_status(self, status: JobStatus) -> list:
        return self.job_repository.get_jobs_by_status(status)
