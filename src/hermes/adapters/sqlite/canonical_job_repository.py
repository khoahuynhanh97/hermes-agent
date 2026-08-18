"""Adapter exposing the canonical durable job repository through the Job port."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from hermes.db import Database
from hermes.domain.job import Job, JobStatus
from hermes.jobs import JobRepository as DurableJobRepository
from hermes.ports.job_repository import JobRepository


class CanonicalJobRepository(JobRepository):
    """Translate the canonical jobs table to the Video/application Job model."""

    def __init__(self, db_path: str):
        self.database = Database(db_path)
        self.database.initialize()
        self.durable = DurableJobRepository(self.database)

    def submit(self, job: Job) -> None:
        owner = str(job.payload.get("owner_user_id") or "system")
        self.durable.enqueue(
            job.id,
            owner,
            job.task_name,
            job.payload,
            max_attempts=int(job.payload.get("max_attempts", 3)),
        )

    def claim(self, worker_id: str, lease_duration_seconds: int) -> Optional[Job]:
        row = self.durable.claim_next(
            worker_id=worker_id,
            lease_duration_seconds=lease_duration_seconds,
        )
        return self._to_job(row) if row else None

    def complete(self, job_id: str, result: dict) -> None:
        self.durable.complete(job_id, result)

    def fail(self, job_id: str, error_message: str) -> None:
        self.durable.fail(job_id, error_message, retryable=False)

    def retry(self, job_id: str) -> None:
        row = self.durable.get(job_id)
        if row:
            self.durable.retry(job_id, row["owner_user_id"])

    def cancel(self, job_id: str) -> None:
        row = self.durable.get(job_id)
        if row:
            self.durable.cancel(job_id, row["owner_user_id"])

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._to_job(self.durable.get(job_id))

    def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        rows = self.durable.list_jobs(limit=500)
        return [job for row in rows if (job := self._to_job(row)) and job.status == status]

    def recover_expired(self) -> list[str]:
        return self.durable.recover_expired()

    @staticmethod
    def _to_job(row: dict | None) -> Optional[Job]:
        if not row:
            return None
        state_map = {
            "queued": JobStatus.QUEUED,
            "running": JobStatus.RUNNING,
            "completed": JobStatus.SUCCEEDED,
            "failed": JobStatus.FAILED,
            "cancelled": JobStatus.CANCELLED,
        }
        parse = lambda value: datetime.fromisoformat(value) if value else None
        payload = dict(row.get("payload") or {})
        payload.setdefault("owner_user_id", row.get("owner_user_id", ""))
        return Job(
            id=row["id"],
            task_name=row["job_type"],
            status=state_map[row["state"]],
            created_at=parse(row["created_at"]),
            updated_at=parse(row["updated_at"]),
            payload=payload,
            result=row.get("result") or None,
            error=row.get("error") or None,
            worker_id=row.get("worker_id"),
            lease_expires_at=parse(row.get("lease_expires_at")),
            attempt=int(row.get("attempts") or 0),
            max_attempts=int(row.get("max_attempts") or 3),
            started_at=parse(row.get("started_at")),
            finished_at=parse(row.get("completed_at")),
        )
