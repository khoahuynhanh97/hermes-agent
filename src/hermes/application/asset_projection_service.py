"""Durable asset projection for Product Research Studio."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
from hermes.runtime_layout import get_data_root, get_product_intelligence_data_root
from hermes.db import Database


class AssetProjectionService:
    """Read production asset projections from durable application state."""

    def __init__(
        self,
        *,
        pi_data_root: str | Path | None = None,
        generated_asset_repository: Optional[SQLiteGeneratedAssetRepository] = None,
        video_factory_repository: Optional[Any] = None,
    ) -> None:
        self._explicit_pi_data_root = Path(pi_data_root).expanduser().resolve() if pi_data_root else None
        self.generated_asset_repository = generated_asset_repository
        self.video_factory_repository = video_factory_repository

    @property
    def pi_data_root(self) -> Path:
        if self._explicit_pi_data_root is not None:
            return self._explicit_pi_data_root
        return Path(get_product_intelligence_data_root() or get_data_root()).expanduser().resolve()

    @classmethod
    def from_runtime(cls) -> "AssetProjectionService":
        configured_db = os.environ.get("HERMES_VIDEO_FACTORY_DB_PATH", "").strip()
        generated_db = Path(configured_db).expanduser().resolve() if configured_db else get_data_root() / "db" / "video_factory.sqlite"
        return cls(
            generated_asset_repository=SQLiteGeneratedAssetRepository(Database(str(generated_db))),
        )

    def find_resource_pack_lock(self, owner_user_id: str, query: str) -> Dict[str, Any] | None:
        """Resolve a persisted PI lock by lock, product, snapshot, or product name."""
        needle = query.strip().lower()
        if not needle:
            return None
        exact_fields = ("lock_id", "resource_pack_id", "snapshot_id", "canonical_product_id")
        fuzzy_fields = ("product_name", "canonical_product_name", "brand", "model")
        for lock in self._pi_locks(owner_user_id):
            if any(str(lock.get(field, "")).lower() == needle for field in exact_fields):
                return dict(lock)
            product_name = str(lock.get("product_name", "")).strip().lower()
            canonical_id = str(lock.get("canonical_product_id", "")).strip().lower()
            brand = str(lock.get("brand", "")).strip().lower()
            model = str(lock.get("model", "")).strip().lower()
            haystack = " ".join(str(lock.get(field, "")) for field in fuzzy_fields).lower()

            if (product_name and product_name in needle) or (canonical_id and canonical_id in needle):
                return dict(lock)
            if brand and model and (f"{brand} {model}" in needle or f"{brand}-{model}" in needle):
                return dict(lock)
            if needle in haystack:
                return dict(lock)

        return None

    def list_resource_pack_locks(self, owner_user_id: str) -> list[Dict[str, Any]]:
        """Return all persisted Product Intelligence resource pack locks."""
        return [dict(lock) for lock in self._pi_locks(owner_user_id)]

    @staticmethod
    def public_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
        """Project internal storage metadata into a browser-safe asset payload."""
        return {
            key: value
            for key, value in asset.items()
            if key not in {"local_path", "_lock_path"}
        }

    def list_products(self, owner_user_id: str, query: str | None = None, limit: int = 50) -> list[Dict[str, Any]]:
        products = []
        needle = (query or "").strip().lower()
        for lock in self._pi_locks(owner_user_id):
            first_asset = next(iter(lock.get("assets", [])), {})
            name = str(lock.get("product_name") or lock.get("canonical_product_name") or lock.get("canonical_product_id") or "")
            if needle and needle not in name.lower():
                continue
            products.append({
                "snapshot_id": lock.get("snapshot_id", ""),
                "research_id": lock.get("research_id", lock.get("run_id", "")),
                "product_id": lock.get("canonical_product_id", ""),
                "product_name": name,
                "brand": lock.get("brand", ""),
                "model": lock.get("model", ""),
                "source_domain": first_asset.get("source_domain", ""),
                "media_count": len(lock.get("assets", [])),
                "created_at": lock.get("created_at", lock.get("locked_at", "")),
                "pack_status": lock.get("status", "locked"),
                "resource_pack_id": lock.get("resource_pack_id", ""),
                "resource_pack_lock_id": lock.get("lock_id", ""),
                "manifest_digest": lock.get("manifest_digest", ""),
            })
        return products[:limit]

    def list_runs(self, owner_user_id: str, status: str | None = None, limit: int = 50) -> list[Dict[str, Any]]:
        runs = []
        for lock in self._pi_locks(owner_user_id):
            run_status = lock.get("research_status", "succeeded")
            if status and run_status != status:
                continue
            runs.append({
                "run_id": lock.get("research_id", lock.get("run_id", lock.get("snapshot_id", ""))),
                "product_name": lock.get("product_name", lock.get("canonical_product_id", "")),
                "status": run_status,
                "snapshot_id": lock.get("snapshot_id", ""),
                "resource_pack_lock_id": lock.get("lock_id", ""),
                "created_at": lock.get("created_at", lock.get("locked_at", "")),
            })
        return runs[:limit]

    def get_product(self, owner_user_id: str, product_or_snapshot_id: str) -> Dict[str, Any] | None:
        for lock in self._pi_locks(owner_user_id):
            ids = {
                str(lock.get("snapshot_id", "")),
                str(lock.get("canonical_product_id", "")),
                str(lock.get("resource_pack_id", "")),
            }
            if product_or_snapshot_id not in ids:
                continue
            assets = self.list_assets(owner_user_id, product_id=lock.get("canonical_product_id"), snapshot_id=lock.get("snapshot_id"))
            return {
                "snapshot_id": lock.get("snapshot_id", ""),
                "overview": {
                    "product_name": lock.get("product_name", lock.get("canonical_product_id", "")),
                    "brand": lock.get("brand", ""),
                    "model": lock.get("model", ""),
                    "canonical_product_id": lock.get("canonical_product_id", ""),
                    "variant_id": lock.get("variant_id", ""),
                    "source_domain": next((asset.get("source_domain", "") for asset in assets if asset.get("source_domain")), ""),
                },
                "research": {
                    "source_url": lock.get("source_url", ""),
                    "usable_sources": lock.get("usable_sources", 0),
                    "status": lock.get("research_status", "succeeded"),
                    "snapshot_id": lock.get("snapshot_id", ""),
                },
                "assets": assets,
                "resource_pack": {
                    "resource_pack_id": lock.get("resource_pack_id", ""),
                    "resource_pack_version": lock.get("resource_pack_version", lock.get("version", 1)),
                    "lock_id": lock.get("lock_id", ""),
                    "manifest_digest": lock.get("manifest_digest", ""),
                    "status": lock.get("status", "locked"),
                },
                "storyboard": self._storyboard_summary(owner_user_id, lock.get("resource_pack_id", "")),
                "generated_media": [asset for asset in assets if asset["role"] == "generated"],
            }
        return None

    def list_assets(
        self,
        owner_user_id: str,
        *,
        role: str | None = None,
        product_id: str | None = None,
        snapshot_id: str | None = None,
        project_id: str | None = None,
        source_domain: str | None = None,
    ) -> list[Dict[str, Any]]:
        assets = [*self._original_assets(owner_user_id), *self._generated_assets(owner_user_id, project_id=project_id), *self._storyboard_assets(owner_user_id)]
        if role:
            assets = [asset for asset in assets if asset["role"] == role]
        if product_id:
            assets = [asset for asset in assets if asset["product_id"] == product_id]
        if snapshot_id:
            assets = [asset for asset in assets if asset["snapshot_id"] == snapshot_id]
        if project_id:
            assets = [asset for asset in assets if asset.get("project_id") == project_id]
        if source_domain:
            assets = [asset for asset in assets if asset["source_domain"] == source_domain]
        return assets

    def get_asset(self, owner_user_id: str, asset_id: str) -> Dict[str, Any] | None:
        for asset in self.list_assets(owner_user_id):
            if asset["asset_id"] == asset_id:
                return asset
        return None

    def resolve_asset_path(self, owner_user_id: str, asset_id: str) -> Path | None:
        asset = self.get_asset(owner_user_id, asset_id)
        if not asset:
            return None
        local_path = str(asset.get("local_path") or "")
        return Path(local_path).expanduser().resolve() if local_path else None

    def _pi_locks(self, owner_user_id: str) -> Iterable[Dict[str, Any]]:
        root = self.pi_data_root / "ProductResearch"
        if not root.exists():
            return []
        locks = []
        for path in root.glob("*/machine/resource-pack-lock.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("status") != "locked":
                continue
            lock_owner = payload.get("owner_user_id", owner_user_id)
            if lock_owner != owner_user_id and lock_owner not in ("user", "system", "default", "anonymous", owner_user_id):
                continue
            payload["_lock_path"] = str(path)
            locks.append(payload)
        return locks

    def _original_assets(self, owner_user_id: str) -> list[Dict[str, Any]]:
        rows = []
        for lock in self._pi_locks(owner_user_id):
            for item in lock.get("assets", []):
                asset_id = str(item.get("asset_id") or item.get("physical_hash_filename") or "")
                if not asset_id:
                    continue
                local_path = str(item.get("local_path") or "")
                rows.append(self._asset_payload(
                    asset_id=asset_id,
                    role=str(item.get("media_role", item.get("role", "original"))),
                    owner_user_id=owner_user_id,
                    product_id=str(lock.get("canonical_product_id", "")),
                    snapshot_id=str(lock.get("snapshot_id", "")),
                    source_domain=str(item.get("source_domain", "")),
                    match_confidence=float(item.get("match_confidence", 0.0)),
                    canonical_product=str(lock.get("product_name", lock.get("canonical_product_id", ""))),
                    variant=str(lock.get("variant_id", "")),
                    physical_hash_filename=str(item.get("physical_hash_filename", Path(local_path).name if local_path else "")),
                    local_path=local_path,
                    resource_pack_lock_id=str(lock.get("lock_id", "")),
                    manifest_digest=str(lock.get("manifest_digest", "")),
                ))
        return rows

    def _generated_assets(self, owner_user_id: str, project_id: str | None = None) -> list[Dict[str, Any]]:
        if self.generated_asset_repository is None:
            return []
        rows = []
        for item in self.generated_asset_repository.list_assets(owner_user_id, project_id=project_id):
            rows.append(self._asset_payload(
                asset_id=str(item["asset_id"]),
                role="generated",
                owner_user_id=owner_user_id,
                product_id=str(item.get("product_id", "")),
                snapshot_id=str(item.get("snapshot_id", "")),
                project_id=str(item.get("project_id", "")),
                source_domain=str(item.get("provider", "video_factory")),
                match_confidence=1.0,
                canonical_product="",
                variant="",
                physical_hash_filename=str(item.get("physical_hash_filename", "")),
                local_path=str(item.get("output_path", "")),
                resource_pack_lock_id=str(item.get("resource_lock_id", "")),
                manifest_digest="",
                status=str(item.get("status", "")) or None,
            ))
        return rows

    def _storyboard_assets(self, owner_user_id: str) -> list[Dict[str, Any]]:
        if self.video_factory_repository is None:
            return []
        rows = []
        for project in self.video_factory_repository.list_owned(owner_user_id):
            if not project.storyboard:
                continue
            for frame in project.storyboard.frames:
                if frame.generated_asset_id:
                    rows.append(self._asset_payload(
                        asset_id=frame.generated_asset_id,
                        role="storyboard_frame",
                        owner_user_id=owner_user_id,
                        product_id=project.resource_pack.product_identity_description if project.resource_pack else "",
                        snapshot_id="",
                        project_id=project.id,
                        source_domain="video_factory",
                        match_confidence=1.0,
                        canonical_product="",
                        variant="",
                        physical_hash_filename=f"frame_{frame.frame_id}.png",
                        local_path="",
                        resource_pack_lock_id=project.resource_pack.id if project.resource_pack else "",
                        manifest_digest="",
                    ))
        return rows

    def _storyboard_summary(self, owner_user_id: str, resource_pack_id: str) -> Dict[str, Any]:
        if self.video_factory_repository is None:
            return {"ready": False, "frames": 0, "status": "none"}
        for project in self.video_factory_repository.list_owned(owner_user_id):
            if project.resource_pack and project.resource_pack.id == resource_pack_id and project.storyboard:
                return {
                    "ready": True,
                    "frames": len(project.storyboard.frames),
                    "status": project.storyboard.approval_status,
                }
        return {"ready": False, "frames": 0, "status": "none"}

    @staticmethod
    def _asset_payload(
        *,
        asset_id: str,
        role: str,
        owner_user_id: str,
        product_id: str,
        snapshot_id: str,
        project_id: str = "",
        source_domain: str,
        match_confidence: float,
        canonical_product: str,
        variant: str,
        physical_hash_filename: str,
        local_path: str,
        resource_pack_lock_id: str,
        manifest_digest: str,
        status: str | None = None,
    ) -> Dict[str, Any]:
        path_exists = bool(local_path and Path(local_path).exists())
        computed_status = "available" if path_exists else "missing"
        return {
            "asset_id": asset_id,
            "role": role,
            "owner_user_id": owner_user_id,
            "product_id": product_id,
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "source_domain": source_domain,
            "match_confidence": match_confidence,
            "canonical_product": canonical_product,
            "variant": variant,
            "physical_hash_filename": physical_hash_filename,
            "local_path": local_path,
            "resource_pack_lock_id": resource_pack_lock_id,
            "manifest_digest": manifest_digest,
            "status": computed_status,
            "content_url": f"/api/assets/{asset_id}/content",
        }
