"""Application-level JobResultProjector for durable domain state projections."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional
from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
from hermes.db import Database


class JobResultProjector:
    """Project terminal job execution results into durable domain state (AssetRepository / Timeline)."""

    def __init__(self, asset_repository: Optional[SQLiteGeneratedAssetRepository] = None):
        self.asset_repository = asset_repository

    def project_terminal_result(
        self,
        job_id: str,
        job_type: str,
        result: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Project terminal job execution into durable domain state. Idempotent by job_id."""
        existing = self.asset_repository.get_by_job_id(job_id) if self.asset_repository is not None else None
        if existing is not None:
            result["durable_asset_id"] = existing["asset_id"]
            result["physical_hash_filename"] = existing["physical_hash_filename"]
            return self._with_terminal_status(job_type, result)

        if job_type in ("image_generate", "video_generate", "tts_generate", "video.cut", "video.render", "export"):
            output_path = result.get("output_path") or result.get("wav_path") or (result.get("output_paths", [""])[0] if result.get("output_paths") else "")
            if not output_path:
                return self._with_terminal_status(job_type, result)

            # Compute physical hash filename if available
            hash_filename = f"sha256_{hashlib.sha256(output_path.encode('utf-8')).hexdigest()[:16]}.media"

            asset_record = {
                "asset_id": f"gen_{job_id}",
                "project_id": payload.get("project_id", "proj_001"),
                "scene_id": payload.get("scene_id", result.get("scene_id", "scene_01")),
                "job_id": job_id,
                "provider": result.get("provider", "local"),
                "resource_lock_id": payload.get("resource_lock_id") or "",
                "reference_asset_ids": payload.get("reference_image_paths", []),
                "prompt_version": payload.get("prompt_version", 1),
                "physical_hash_filename": hash_filename,
                "output_path": output_path,
                "status": "completed",
            }

            if self.asset_repository is not None:
                self.asset_repository.save_asset(asset_record)

            result["durable_asset_id"] = asset_record["asset_id"]
            result["physical_hash_filename"] = hash_filename

        return self._with_terminal_status(job_type, result)

    @staticmethod
    def _with_terminal_status(job_type: str, result: Dict[str, Any]) -> Dict[str, Any]:
        if job_type == "video_generate":
            result["scene_status"] = "completed"
        elif job_type == "tts_generate":
            result["timeline_reference"] = result.get("durable_asset_id")
        elif job_type == "video.render":
            result["timeline_render_status"] = "completed"
        elif job_type == "export":
            result["project_export_status"] = "completed"
        return result
