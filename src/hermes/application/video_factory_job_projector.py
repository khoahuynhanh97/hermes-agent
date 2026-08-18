from __future__ import annotations

from hermes.domain.generated_asset import GeneratedAsset
from hermes.ports.generated_asset_repository import GeneratedAssetRepository
from hermes.ports.job_repository import JobRepository
from hermes.ports.video_factory_repository import VideoFactoryRepository


class VideoFactoryJobProjector:
    def __init__(
        self,
        job_repository: JobRepository,
        project_repository: VideoFactoryRepository,
        asset_repository: GeneratedAssetRepository,
    ):
        self.job_repository = job_repository
        self.project_repository = project_repository
        self.asset_repository = asset_repository

    def project_next_event(self) -> dict | None:
        event = self.job_repository.claim_event("video-factory-projector", 300)
        if not event:
            return None

        job_id = event["job_id"]
        job = self.job_repository.get(job_id)
        if not job or job["state"] != "completed":
            self.job_repository.release_event(event["event_id"])
            return None

        result = event["payload"]["result"]
        asset = GeneratedAsset(
            asset_id=result["asset_id"],
            owner_user_id=job["owner_user_id"],
            project_id=result["project_id"],
            job_id=job_id,
            artifact_type=result["artifact_type"],
            artifact_id=result["artifact_id"],
            artifact_version=job["payload"].get("version", 1),
            storage_key=result["storage_key"],
            mime_type=result["mime_type"],
            checksum_sha256=result["checksum_sha256"],
        )
        self.asset_repository.save(asset)

        project = self.project_repository.get(job["owner_user_id"], result["project_id"])
        if project:
            if asset.artifact_type == "frame_image":
                for frame in project.storyboard.frames:
                    if frame.frame_id == asset.artifact_id:
                        frame.generated_asset_id = asset.asset_id
                        break
            self.project_repository.save(project)

        self.job_repository.ack_event(event["event_id"])
        return {"event_id": event["event_id"], "delivery_state": "delivered"}
