from __future__ import annotations

import pytest

from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
from hermes.adapters.sqlite.job_repository import SQLiteJobRepository
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_job_projector import VideoFactoryJobProjector
from hermes.db import Database


class ProjectorFixture:
    def __init__(self, tmp_path):
        db_path = tmp_path / "hermes.sqlite"
        self.database = Database(db_path)
        self.job_repository = SQLiteJobRepository(self.database)
        self.project_repository = SQLiteVideoFactoryRepository(self.database)
        self.asset_repository = SQLiteGeneratedAssetRepository(self.database)
        self.projector = VideoFactoryJobProjector(
            job_repository=self.job_repository,
            project_repository=self.project_repository,
            asset_repository=self.asset_repository,
        )
        self.asset_id = "asset-123"

    def complete_frame_job(self):
        self.job_repository.enqueue("job-1", "owner-1", "video.frame.generate", {"project_id": "p1", "frame_id": "f1"})
        self.job_repository.claim_next()
        self.job_repository.complete(
            "job-1",
            {
                "asset_id": self.asset_id,
                "project_id": "p1",
                "artifact_type": "frame_image",
                "artifact_id": "f1",
                "storage_key": "path/to/image.png",
                "mime_type": "image/png",
                "checksum_sha256": "abc",
            },
        )

    def run_projector_once(self):
        return self.projector.project_next_event()


@pytest.fixture
def projector_fixture(tmp_path):
    return ProjectorFixture(tmp_path)


def test_completed_frame_updates_project_when_no_ui_is_running(projector_fixture):
    projector_fixture.complete_frame_job()
    projector_fixture.run_projector_once()
    project = projector_fixture.project_repository.get("owner-1", "p1")
    assert project.storyboard.frames[0].generated_asset_id == projector_fixture.asset_id
    assert projector_fixture.asset_repository.get("owner-1", projector_fixture.asset_id) is not None
