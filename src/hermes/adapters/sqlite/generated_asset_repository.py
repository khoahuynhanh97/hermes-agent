from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Optional

from hermes.db import Database
from hermes.domain.generated_asset import GeneratedAsset


class SQLiteGeneratedAssetRepository:
    def __init__(self, database: Database):
        self._database = database
        self._database.initialize()

    def save(self, asset: GeneratedAsset) -> None:
        with self._database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO video_factory_generated_assets (
                    asset_id, owner_user_id, project_id, job_id, artifact_type, artifact_id,
                    artifact_version, storage_key, mime_type, checksum_sha256,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(asset_id) DO UPDATE SET
                    owner_user_id=excluded.owner_user_id,
                    project_id=excluded.project_id,
                    job_id=excluded.job_id,
                    artifact_type=excluded.artifact_type,
                    artifact_id=excluded.artifact_id,
                    artifact_version=excluded.artifact_version,
                    storage_key=excluded.storage_key,
                    mime_type=excluded.mime_type,
                    checksum_sha256=excluded.checksum_sha256
                """,
                (
                    asset.asset_id,
                    asset.owner_user_id,
                    asset.project_id,
                    asset.job_id,
                    asset.artifact_type,
                    asset.artifact_id,
                    asset.artifact_version,
                    asset.storage_key,
                    asset.mime_type,
                    asset.checksum_sha256,
                ),
            )

    def save_asset(self, asset: dict) -> None:
        """Save the browser/job-facing generated asset projection."""
        output_path = str(asset.get("output_path") or asset.get("storage_key") or "")
        physical_name = str(asset.get("physical_hash_filename") or Path(output_path).name or asset.get("asset_id") or "")
        params = {
            "scene_id": asset.get("scene_id", ""),
            "resource_lock_id": asset.get("resource_lock_id", ""),
            "reference_asset_ids": asset.get("reference_asset_ids", []),
            "prompt_version": asset.get("prompt_version", 1),
            "physical_hash_filename": physical_name,
            "output_path": output_path,
            "status": asset.get("status", "completed"),
        }
        artifact_type = str(asset.get("artifact_type") or _infer_artifact_type(output_path))
        checksum = str(asset.get("checksum_sha256") or hashlib.sha256(output_path.encode("utf-8")).hexdigest())
        with self._database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO video_factory_generated_assets (
                    asset_id, project_id, owner_user_id, job_id, artifact_type,
                    artifact_id, artifact_version, storage_key, mime_type,
                    checksum_sha256, provider, provider_generation_id,
                    width, height, duration_seconds, generation_params_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(asset_id) DO UPDATE SET
                    project_id=excluded.project_id,
                    owner_user_id=excluded.owner_user_id,
                    job_id=excluded.job_id,
                    artifact_type=excluded.artifact_type,
                    artifact_id=excluded.artifact_id,
                    artifact_version=excluded.artifact_version,
                    storage_key=excluded.storage_key,
                    mime_type=excluded.mime_type,
                    checksum_sha256=excluded.checksum_sha256,
                    provider=excluded.provider,
                    provider_generation_id=excluded.provider_generation_id,
                    width=excluded.width,
                    height=excluded.height,
                    duration_seconds=excluded.duration_seconds,
                    generation_params_json=excluded.generation_params_json
                """,
                (
                    str(asset["asset_id"]),
                    str(asset.get("project_id") or ""),
                    str(asset.get("owner_user_id") or "user"),
                    str(asset.get("job_id") or ""),
                    artifact_type,
                    str(asset.get("artifact_id") or asset.get("scene_id") or ""),
                    int(asset.get("artifact_version") or 1),
                    output_path,
                    str(asset.get("mime_type") or _mime_type(output_path)),
                    checksum,
                    str(asset.get("provider") or ""),
                    str(asset.get("provider_generation_id") or ""),
                    asset.get("width"),
                    asset.get("height"),
                    asset.get("duration_seconds"),
                    json.dumps(params, ensure_ascii=False),
                ),
            )

    def get(self, owner_user_id: str, asset_id: str) -> Optional[GeneratedAsset]:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM video_factory_generated_assets WHERE owner_user_id = ? AND asset_id = ?",
                (owner_user_id, asset_id),
            ).fetchone()
            return self._to_domain(row) if row else None

    def find_by_job(self, owner_user_id: str, job_id: str) -> Optional[GeneratedAsset]:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM video_factory_generated_assets WHERE owner_user_id = ? AND job_id = ?",
                (owner_user_id, job_id),
            ).fetchone()
            return self._to_domain(row) if row else None

    def get_by_job_id(self, job_id: str) -> Optional[dict]:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM video_factory_generated_assets WHERE job_id = ? ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            return self._to_payload(row) if row else None

    def get_by_asset_id(self, asset_id: str) -> Optional[dict]:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM video_factory_generated_assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            return self._to_payload(row) if row else None

    def count_by_job_id(self, job_id: str) -> int:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM video_factory_generated_assets WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            return int(row["total"] if row else 0)

    def list_assets(self, owner_user_id: str | None = None, project_id: str | None = None) -> list[dict]:
        where = []
        params = []
        if owner_user_id:
            where.append("owner_user_id = ?")
            params.append(owner_user_id)
        if project_id:
            where.append("project_id = ?")
            params.append(project_id)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._database.transaction() as connection:
            rows = connection.execute(
                f"SELECT * FROM video_factory_generated_assets {clause} ORDER BY created_at DESC",
                tuple(params),
            ).fetchall()
            return [self._to_payload(row) for row in rows]

    def _to_domain(self, row: dict) -> GeneratedAsset:
        return GeneratedAsset(
            asset_id=row["asset_id"],
            owner_user_id=row["owner_user_id"],
            project_id=row["project_id"],
            job_id=row["job_id"],
            artifact_type=row["artifact_type"],
            artifact_id=row["artifact_id"],
            artifact_version=row["artifact_version"],
            storage_key=row["storage_key"],
            mime_type=row["mime_type"],
            checksum_sha256=row["checksum_sha256"],
        )

    @staticmethod
    def _to_payload(row: dict) -> dict:
        params = json.loads(row["generation_params_json"] or "{}")
        output_path = params.get("output_path") or row["storage_key"] or ""
        return {
            "asset_id": row["asset_id"],
            "owner_user_id": row["owner_user_id"],
            "project_id": row["project_id"],
            "scene_id": params.get("scene_id") or row["artifact_id"],
            "job_id": row["job_id"],
            "provider": row["provider"] or "",
            "resource_lock_id": params.get("resource_lock_id", ""),
            "reference_asset_ids": params.get("reference_asset_ids", []),
            "prompt_version": params.get("prompt_version", 1),
            "physical_hash_filename": params.get("physical_hash_filename") or Path(output_path).name,
            "output_path": output_path,
            "artifact_type": row["artifact_type"],
            "artifact_id": row["artifact_id"],
            "artifact_version": row["artifact_version"],
            "storage_key": row["storage_key"],
            "mime_type": row["mime_type"],
            "checksum_sha256": row["checksum_sha256"],
            "status": params.get("status", "completed"),
            "created_at": row["created_at"],
        }


def _infer_artifact_type(output_path: str) -> str:
    suffix = Path(output_path).suffix.lower()
    if suffix in {".mp4", ".mov", ".mkv", ".webm"}:
        return "scene_video"
    return "frame_image"


def _mime_type(output_path: str) -> str:
    suffix = Path(output_path).suffix.lower()
    if suffix == ".mp4":
        return "video/mp4"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".wav":
        return "audio/wav"
    return "application/octet-stream"
