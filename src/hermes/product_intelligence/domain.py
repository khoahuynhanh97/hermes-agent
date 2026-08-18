from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal
from pathlib import Path

class Asset(BaseModel):
    """Represents a single asset within the resource pack."""
    asset_id: str
    asset_type: Literal["image", "video", "document", "review_data"]
    path_in_pack: str
    description: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    
    # This field is not part of the lock file, but populated by the projection service
    physical_path: Optional[Path] = None
    physical_status: Literal["available", "missing"] = "missing"


class ResourcePackLock(BaseModel):
    """Defines the structure of a resource pack lock file."""
    pack_id: str
    product_sku: str
    manifest_digest: str  # SHA256 digest of the manifest content
    assets: List[Asset]


class ProductInfo(BaseModel):
    """Represents structured product information extracted from PI data."""
    sku: str
    name: str
    usps: List[str]  # Unique Selling Propositions
    specs: Dict[str, str]
    positive_feedback: List[str]
    negative_feedback: List[str]
