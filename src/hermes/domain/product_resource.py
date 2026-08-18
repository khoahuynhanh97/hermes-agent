"""Domain definitions for ProjectResourceBinding and ProductionResourceSet."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ProjectResourceBinding:
    project_id: str
    source_system: str
    resource_pack_id: str
    lock_version: int
    manifest_digest: str
    canonical_product_id: str
    variant_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.project_id.strip() or not self.resource_pack_id.strip():
            raise ValueError("project_id and resource_pack_id are required")
        if not self.manifest_digest.strip():
            raise ValueError("manifest_digest is required")


@dataclass(frozen=True)
class ProductionResourceSet:
    id: str
    owner_user_id: str
    product_references: tuple[Any, ...]
    primary_product_asset_id: str
    product_identity_description: str
    locked_product_identity: Any | None = None
    character_references: tuple[Any, ...] = ()
    primary_character_asset_id: str | None = None
    character_identity_description: str = ""
    locked_character_identity: Any | None = None
    default_outfit: str = ""
    context: str = ""
    visual_style: str = ""
    locked_at: str | None = None
    version: int = 1
