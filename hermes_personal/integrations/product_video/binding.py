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
    """Legacy wrapper (deprecated). Delegates to service.create_binding to avoid
    duplicate hashing logic."""
    return ProductVideoBindingService().create_binding(product_id, resource_pack)


def verify_binding_integrity(binding: ProductVideoBinding, current_resource_pack: dict) -> bool:
    """Legacy integrity check (deprecated). Use ArtifactRef.digest directly."""
    import hashlib, json
    payload = json.dumps(current_resource_pack, sort_keys=True).encode()
    current_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return binding.lock_ref is not None and current_digest == binding.lock_ref.digest