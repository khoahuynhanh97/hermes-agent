from __future__ import annotations

import json, hashlib
from dataclasses import asdict

from hermes_personal.integrations.video_factory.client import VideoFactoryClient


class ProductVideoBinding:
    """Immutable binding between a locked product resource pack and a video artifact.

    Stores:
    - product_id: identifier of the product resource.
    - resource_pack_digest: sha256 of the locked resource pack dict (stable integrity token).
    - artifact_ref: deterministic reference from VideoFactoryClient.
    """

    def __init__(self, product_id: str, resource_pack_digest: str, artifact_ref: str) -> None:
        self.product_id = product_id
        self.resource_pack_digest = resource_pack_digest
        self.artifact_ref = artifact_ref

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "resource_pack_digest": self.resource_pack_digest,
            "artifact_ref": self.artifact_ref,
        }


class ProductVideoBindingService:
    """Service to create and manage ProductVideoBinding instances.

    Relies on deterministic VideoFactoryClient; no external I/O.
    """

    def __init__(self) -> None:
        self.video_client = VideoFactoryClient()

    def _digest_resource_pack(self, pack: dict) -> str:
        payload = json.dumps(pack, sort_keys=True).encode()
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def create_binding(self, product_id: str, resource_pack: dict) -> ProductVideoBinding:
        """Create binding for given product and its locked resource pack.

        Generates a deterministic artifact reference via a dummy creative brief call.
        """
        # deterministic artifact reference – use any client method; creative brief suffices
        artifact_info = self.video_client.create_creative_brief()
        artifact_ref = artifact_info["artifact_ref"]
        pack_digest = self._digest_resource_pack(resource_pack)
        return ProductVideoBinding(product_id, pack_digest, artifact_ref)


def verify_binding_integrity(binding: ProductVideoBinding, current_resource_pack: dict) -> bool:
    """Return True if current_resource_pack matches the digest stored in binding.

    Mismatch indicates invalidation; caller may raise or act accordingly.
    """
    payload = json.dumps(current_resource_pack, sort_keys=True).encode()
    current_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return current_digest == binding.resource_pack_digest
