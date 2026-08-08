from abc import ABC, abstractmethod
from typing import Optional, List
from hermes.domain.job import Job, JobStatus

class JobRepository(ABC):
    @abstractmethod
    def submit(self, job: Job) -> None:
        pass

    @abstractmethod
    def claim(self, worker_id: str, lease_duration_seconds: int) -> Optional[Job]:
        pass

    @abstractmethod
    def complete(self, job_id: str, result: dict) -> None:
        pass

    @abstractmethod
    def fail(self, job_id: str, error_message: str) -> None:
        pass

    @abstractmethod
    def retry(self, job_id: str) -> None:
        pass

    @abstractmethod
    def cancel(self, job_id: str) -> None:
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        pass

    @abstractmethod
    def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        pass
