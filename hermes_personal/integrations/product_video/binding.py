from __future__ import annotations

from hermes_personal.product_video.binding import (
    ArtifactRef,
    ProductVideoBinding,
    ProductVideoBindingService,
)

__all__ = [
    "ArtifactRef",
    "ProductVideoBinding",
    "ProductVideoBindingService",
    "create_binding",
    "verify_binding_integrity",
]


def create_binding(product_id: str, resource_pack: dict) -> ProductVideoBinding:
    """Legacy wrapper (deprecated). Use ProductVideoBindingService directly."""
    import hashlib, json
    digest = "sha256:" + hashlib.sha256(
        json.dumps(resource_pack, sort_keys=True).encode()
    ).hexdigest()
    lock_ref = ArtifactRef(artifact_id=product_id, version=1, digest=digest, owner="product_intelligence")
    return ProductVideoBindingService().create(product_id, lock_ref)


def verify_binding_integrity(binding: ProductVideoBinding, current_resource_pack: dict) -> bool:
    """Legacy integrity check (deprecated). Use ArtifactRef.digest directly."""
    import hashlib, json
    payload = json.dumps(current_resource_pack, sort_keys=True).encode()
    current_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return binding.lock_ref is not None and current_digest == binding.lock_ref.digest