import pytest
from hermes.application.video_service import VideoService
from hermes.adapters.sqlite.job_repository import SQLiteJobRepository
from hermes.domain.job import JobStatus


@pytest.fixture
def job_repo(tmp_path):
    db_path = tmp_path / "test.db"
    return SQLiteJobRepository(str(db_path))


@pytest.fixture
def service(job_repo):
    return VideoService(job_repo)


def test_video_cut_submits_a_local_capability_job(service):
    result = service.request_cut("asset-1", 0, 10)
    assert result.ok
    assert result.value.task_name == "video.cut"


def test_video_render_submits_a_job(service):
    result = service.request_render("asset-2", "mp4")
    assert result.ok
    assert result.value.task_name == "video.render"


def test_get_jobs_by_status(service):
    service.request_cut("asset-1", 0, 10)
    service.request_cut("asset-2", 5, 15)

    jobs = service.get_jobs_by_status(JobStatus.QUEUED)
    assert len(jobs) == 2
