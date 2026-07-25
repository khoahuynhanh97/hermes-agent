import pytest
import time
from datetime import datetime, timedelta
from hermes.domain.job import Job, JobStatus
from hermes.adapters.sqlite.job_repository import SQLiteJobRepository
from hermes.application.job_service import JobService

@pytest.fixture
def in_memory_job_repo(tmp_path):
    db_path = tmp_path / "test_jobs.db"
    repo = SQLiteJobRepository(str(db_path))
    yield repo
    
@pytest.fixture
def job_service(in_memory_job_repo):
    return JobService(in_memory_job_repo)

def test_job_lifecycle(job_service: JobService, in_memory_job_repo: SQLiteJobRepository):
    # Submit a job
    job_id = job_service.submit_job("test_task", {"input": 123})
    assert job_service.repository.get_job(job_id).status == JobStatus.QUEUED

    # Claim the job by worker 1
    worker1_id = "worker-1"
    claimed_job = job_service.claim_job(worker1_id, lease_duration_seconds=1)
    assert claimed_job is not None
    assert claimed_job.id == job_id
    assert claimed_job.status == JobStatus.RUNNING
    assert claimed_job.worker_id == worker1_id
    
    # Verify job status in repository
    job_in_db = in_memory_job_repo.get_job(job_id)
    assert job_in_db.status == JobStatus.RUNNING
    assert job_in_db.worker_id == worker1_id
    assert job_in_db.lease_expires_at is not None
    
    # Worker 2 tries to claim a job, but worker 1 still holds the lease
    worker2_id = "worker-2"
    no_job = job_service.claim_job(worker2_id, lease_duration_seconds=1)
    assert no_job is None

    # Wait for lease to expire
    time.sleep(1.1)

    # Worker 2 can now claim the job
    claimed_job_by_worker2 = job_service.claim_job(worker2_id, lease_duration_seconds=1)
    assert claimed_job_by_worker2 is not None
    assert claimed_job_by_worker2.id == job_id
    assert claimed_job_by_worker2.status == JobStatus.RUNNING
    assert claimed_job_by_worker2.worker_id == worker2_id

    # Complete the job
    job_service.complete_job(job_id, {"output": 456})
    completed_job = job_service.repository.get_job(job_id)
    assert completed_job.status == JobStatus.SUCCEEDED
    assert completed_job.result == {"output": 456}

    # Fail a job
    job_id_fail = job_service.submit_job("another_task", {})
    job_service.claim_job(worker1_id, lease_duration_seconds=1) # claim it
    job_service.fail_job(job_id_fail, "Something went wrong")
    failed_job = job_service.repository.get_job(job_id_fail)
    assert failed_job.status == JobStatus.FAILED
    assert failed_job.error == "Something went wrong"

    # Retry a failed job
    job_service.repository.retry(job_id_fail)
    retried_job = job_service.repository.get_job(job_id_fail)
    assert retried_job.status == JobStatus.QUEUED
    assert retried_job.worker_id is None
    assert retried_job.lease_expires_at is None

    # Cancel a job
    job_id_cancel = job_service.submit_job("cancel_task", {})
    job_service.repository.cancel(job_id_cancel)
    cancelled_job = job_service.repository.get_job(job_id_cancel)
    assert cancelled_job.status == JobStatus.CANCELLED
