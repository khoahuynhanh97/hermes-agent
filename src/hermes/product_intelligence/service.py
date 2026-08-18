import json
import hashlib
from pathlib import Path
from typing import Optional, List

from .domain import ResourcePackLock, ProductInfo, Asset
from ..runtime_layout import get_product_intelligence_data_root

class AssetProjectionService:
    """
    Handles loading, validating, and projecting assets from Product Intelligence.
    """
    def __init__(self, pi_data_root: Optional[Path] = None):
        self.pi_data_root = pi_data_root or get_product_intelligence_data_root()
        if not self.pi_data_root:
            raise ValueError("HERMES_PI_DATA_DIR is not set. Cannot access Product Intelligence data.")

    def load_and_verify_resource_pack(self, product_sku: str) -> Optional[ResourcePackLock]:
        """
        Loads the resource pack for a given SKU, verifies its integrity, 
        and projects physical asset paths.
        """
        pack_dir = self.pi_data_root / "products" / product_sku
        lock_file_path = pack_dir / "hermes_lock.json"

        if not lock_file_path.exists():
            return None

        # 1. Load the lock file
        try:
            with open(lock_file_path, 'r', encoding='utf-8') as f:
                lock_data = json.load(f)
            pack_lock = ResourcePackLock.model_validate(lock_data)
        except (json.JSONDecodeError, ValueError) as e:
            # Handle Pydantic validation error as well
            print(f"Error reading or validating lock file for {product_sku}: {e}")
            return None
            
        # 2. Verify manifest_digest
        assets_json_str = json.dumps([asset.model_dump(exclude={'physical_path', 'physical_status'}) for asset in pack_lock.assets], sort_keys=True, ensure_ascii=False)
        calculated_digest = hashlib.sha256(assets_json_str.encode('utf-8')).hexdigest()

        if calculated_digest != pack_lock.manifest_digest:
            print(f"Digest mismatch for {product_sku}. Data may be tampered. Lock: {pack_lock.manifest_digest}, Calc: {calculated_digest}")
            return None

        # 3. Project physical paths and check status
        for asset in pack_lock.assets:
            physical_path = (pack_dir / asset.path_in_pack).resolve()
            asset.physical_path = physical_path
            if physical_path.exists() and physical_path.is_file():
                asset.physical_status = "available"
            else:
                asset.physical_status = "missing"
        
        return pack_lock

class ProductScoutService:
    """
    Allows agents to scout for product information.
    """
    def __init__(self, pi_data_root: Optional[Path] = None):
        self.pi_data_root = pi_data_root or get_product_intelligence_data_root()
        if not self.pi_data_root:
            raise ValueError("HERMES_PI_DATA_DIR is not set. Cannot access Product Intelligence data.")
    
    def scout_by_sku(self, sku: str) -> Optional[ProductInfo]:
        """
        Extracts key product highlights (USPs, specs, feedback) for a given SKU.
        
        In a real implementation, this would parse various files (specs.csv, reviews.json, etc.).
        Here, we'll simulate it by looking for a 'product_info.json'.
        """
        product_dir = self.pi_data_root / "products" / sku
        info_file = product_dir / "product_info.json"
        
        if not info_file.exists():
            return None
            
        try:
            with open(info_file, 'r', encoding='utf-8') as f:
                info_data = json.load(f)
            
            # Assuming the JSON directly matches the ProductInfo model
            return ProductInfo.model_validate(info_data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error reading or validating product info for {sku}: {e}")
            return None
