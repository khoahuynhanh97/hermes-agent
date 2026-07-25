from hermes.domain.job import Job, JobStatus
from hermes.ports.job_repository import JobRepository
from typing import Dict, Any, Optional


class JobService:
    def __init__(self, repository: JobRepository):
        self.repository = repository

    def submit_job(self, task_name: str, payload: Dict[str, Any]) -> str:
        job = Job.new(task_name, payload)
        self.repository.submit(job)
        return job.id

    def claim_job(self, worker_id: str, lease_duration_seconds: int = 30) -> Optional[Job]:
        return self.repository.claim(worker_id, lease_duration_seconds)

    def complete_job(self, job_id: str, result: Dict[str, Any]) -> None:
        self.repository.complete(job_id, result)

    def fail_job(self, job_id: str, error: str) -> None:
        self.repository.fail(job_id, error)

    def retry_job(self, job_id: str) -> None:
        self.repository.retry(job_id)

    def cancel_job(self, job_id: str) -> None:
        self.repository.cancel(job_id)

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.repository.get_job(job_id)

    def get_jobs_by_status(self, status: JobStatus) -> list:
        return self.repository.get_jobs_by_status(status)
