"""ProductResourceService for Hermes Resource Binding and Anti-Corruption Adapter."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from hermes.domain.product_resource import ProjectResourceBinding, ProductionResourceSet


class ProductResourceService:
    """Service to verify Product Intelligence locks and produce ProductionResourceSets for Video Factory."""

    def __init__(self, repository: Optional[Any] = None):
        self.repository = repository

    @staticmethod
    def canonical_manifest(pi_lock_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return immutable production-relevant manifest content for lock digesting."""
        return {
            "resource_pack_id": pi_lock_payload.get("resource_pack_id"),
            "resource_pack_version": pi_lock_payload.get("resource_pack_version", pi_lock_payload.get("version", 1)),
            "snapshot_id": pi_lock_payload.get("snapshot_id"),
            "canonical_product_id": pi_lock_payload.get("canonical_product_id"),
            "variant_id": pi_lock_payload.get("variant_id"),
            "claims": pi_lock_payload.get("claims", []),
            "identity_constraints": pi_lock_payload.get(
                "identity_constraints",
                pi_lock_payload.get("identity", pi_lock_payload.get("product_identity", {})),
            ),
            "assets": pi_lock_payload.get("assets", []),
        }

    @classmethod
    def compute_manifest_digest(cls, pi_lock_payload: Dict[str, Any]) -> str:
        manifest_content = json.dumps(
            cls.canonical_manifest(pi_lock_payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"sha256:{hashlib.sha256(manifest_content.encode('utf-8')).hexdigest()}"

    def lock_resource_pack(self, pi_lock_payload: Dict[str, Any], owner_user_id: str = "user") -> Dict[str, Any]:
        payload = dict(pi_lock_payload)
        payload["manifest_digest"] = self.compute_manifest_digest(payload)
        payload["status"] = "locked"
        version = int(payload.get("resource_pack_version", payload.get("version", 1)))
        if self.repository is not None and hasattr(self.repository, "save_resource_pack_lock"):
            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            payload["lock_id"] = self.repository.save_resource_pack_lock(
                payload_json,
                owner_user_id,
                str(payload["resource_pack_id"]),
                version,
                payload["manifest_digest"],
            )
        elif not payload.get("lock_id"):
            payload["lock_id"] = f"lock_{payload['resource_pack_id']}_v{version}"
        return payload

    def verify_and_bind(
        self,
        project_id: str,
        pi_lock_payload: Dict[str, Any],
        owner_user_id: str = "user",
    ) -> ProjectResourceBinding:
        """Verify immutable PI lock, validate manifest digest, and create ProjectResourceBinding."""
        status = pi_lock_payload.get("status")
        if status != "locked":
            raise ValueError("PI lock must have status 'locked'")

        lock_id = pi_lock_payload.get("lock_id")
        resource_pack_id = pi_lock_payload.get("resource_pack_id")
        manifest_digest = pi_lock_payload.get("manifest_digest")

        if not lock_id or not resource_pack_id or not manifest_digest:
            raise ValueError("PI lock missing required lock_id, resource_pack_id, or manifest_digest")

        computed_digest = self.compute_manifest_digest(pi_lock_payload)
        if computed_digest != manifest_digest:
            raise ValueError(f"Manifest digest mismatch: expected {manifest_digest}, got {computed_digest}")

        binding = ProjectResourceBinding(
            project_id=project_id,
            source_system="product_intelligence",
            resource_pack_id=resource_pack_id,
            lock_version=pi_lock_payload.get("version", 1),
            manifest_digest=manifest_digest,
            canonical_product_id=pi_lock_payload.get("canonical_product_id", "prod_001"),
            variant_id=pi_lock_payload.get("variant_id"),
        )

        if self.repository is not None:
            self.repository.save(binding, owner_user_id=owner_user_id, resource_lock_id=lock_id)

        return binding

    def rebind_project_resource(
        self,
        project_id: str,
        pi_lock_payload: Dict[str, Any],
        owner_user_id: str = "user",
    ) -> ProjectResourceBinding:
        """Explicitly rebind a project to a new Product Intelligence lock."""
        status = pi_lock_payload.get("status")
        if status != "locked":
            raise ValueError("PI lock must have status 'locked'")

        lock_id = pi_lock_payload.get("lock_id")
        resource_pack_id = pi_lock_payload.get("resource_pack_id")
        manifest_digest = pi_lock_payload.get("manifest_digest")
        computed_digest = self.compute_manifest_digest(pi_lock_payload)
        if computed_digest != manifest_digest:
            raise ValueError(f"Manifest digest mismatch: expected {manifest_digest}, got {computed_digest}")

        binding = ProjectResourceBinding(
            project_id=project_id,
            source_system="product_intelligence",
            resource_pack_id=resource_pack_id,
            lock_version=pi_lock_payload.get("version", 1),
            manifest_digest=manifest_digest,
            canonical_product_id=pi_lock_payload.get("canonical_product_id", "prod_001"),
            variant_id=pi_lock_payload.get("variant_id"),
        )

        if self.repository is not None:
            self.repository.save(binding, owner_user_id=owner_user_id, resource_lock_id=lock_id, allow_rebind=True)

        return binding

    def unbind_project_resource(self, project_id: str, owner_user_id: str = "user") -> None:
        """Unbind an active resource lock from a project."""
        if self.repository is not None:
            self.repository.unbind(project_id, owner_user_id=owner_user_id)

    def archive_project_resource(self, project_id: str, owner_user_id: str = "user") -> None:
        """Archive a project resource binding."""
        if self.repository is not None:
            self.repository.archive(project_id, owner_user_id=owner_user_id)

    def to_production_resource_set(
        self,
        binding: ProjectResourceBinding,
        pi_lock_payload: Dict[str, Any],
        owner_user_id: str = "user",
    ) -> ProductionResourceSet:
        """Anti-corruption adapter converting ProjectResourceBinding & PI lock to Video Factory ProductionResourceSet."""
        assets = pi_lock_payload.get("assets", [])
        product_refs = tuple(
            {
                "asset_id": asset["asset_id"],
                "uri": asset.get("local_path", f"/data/{asset['asset_id']}.jpg"),
                "metadata": {
                    "source_domain": asset.get("source_domain", ""),
                    "match_confidence": asset.get("match_confidence", 1.0),
                    "physical_hash": asset.get("physical_hash_filename", ""),
                },
            }
            for asset in assets
        )
        primary_asset_id = product_refs[0]["asset_id"] if product_refs else "asset_01"

        return ProductionResourceSet(
            id=f"prs_{binding.project_id}",
            owner_user_id=owner_user_id,
            product_references=product_refs,
            primary_product_asset_id=primary_asset_id,
            product_identity_description=f"Canonical Product {binding.canonical_product_id}",
            context="Video Factory Bound Context",
            version=binding.lock_version,
        )
