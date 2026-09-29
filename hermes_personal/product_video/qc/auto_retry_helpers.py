"""Auto-Retry Image QC helper functions for cleanable failure detection and recovery."""

from __future__ import annotations

from typing import Any

from hermes_personal.product_video.qc.models import QCReport, QCVerdict


def is_cleanable_failure(qc_report: QCReport) -> bool:
    """Determine if Image QC failure is recoverable via image cleaning (inpainting).
    
    Cleanable failures are caused by:
    - Watermarks / seller branding
    - Text overlays / promotional banners
    - Marketplace badges
    - Shop domain URLs
    
    Non-cleanable (terminal) failures:
    - Missing or corrupted image files
    - Insufficient image resolution
    - No eligible images at all (score < 20)
    - Fundamental product identity issues
    
    Args:
        qc_report: Image QC report with verdict FAIL
        
    Returns:
        True if failure is cleanable via inpainting, False if terminal
    """
    # Must be a FAIL verdict
    if qc_report.verdict != QCVerdict.FAIL:
        return False
    
    # Score too low indicates fundamental issues (missing files, corrupted, etc.)
    if qc_report.score < 20:
        return False
    
    # Check recovery actions - "reacquire_references" means we need new images
    recovery_actions = qc_report.findings.get("recovery_actions", [])
    if "reacquire_references" in recovery_actions:
        return False
    
    # Check if any failed items have cleanable risk flags
    items = qc_report.findings.get("items", [])
    failed_items = [it for it in items if not it.get("eligible")]
    
    cleanable_risks = {"watermark", "logo", "text_overlay", "banner", "badge", "shop_domain"}
    
    for item in failed_items:
        if not isinstance(item, dict):
            continue
        
        findings = item.get("findings", {})
        if not isinstance(findings, dict):
            continue
            
        risk_flags = findings.get("risk_flags", [])
        if not isinstance(risk_flags, list):
            continue
        
        item_risks = set(risk_flags)
        if item_risks & cleanable_risks:
            return True  # Found at least one cleanable issue
    
    return False


def extract_artifacts_from_qc(qc_report: QCReport) -> list[dict[str, Any]]:
    """Extract detected artifact categories from QC findings for targeted inpainting.
    
    Maps QC risk flags to ProductImageCleaner ArtifactCategory enum values.
    
    Args:
        qc_report: Image QC report with detected issues
        
    Returns:
        List of artifact descriptors for image cleaner:
        [
            {
                "asset_id": "img_001",
                "category": "GENERIC_WATERMARK",
                "confidence": 0.95,
                "bounding_boxes": [...]  # Optional, if available
            },
            ...
        ]
    """
    items = qc_report.findings.get("items", [])
    
    # Map QC risk flags to ProductImageCleaner categories
    category_map = {
        "watermark": "GENERIC_WATERMARK",
        "logo": "SELLER_BRANDING",
        "text_overlay": "SPEC_CALLOUT_OVERLAY",
        "banner": "PROMOTIONAL_TAG",
        "badge": "MARKETPLACE_BADGE",
        "shop_domain": "SHOP_DOMAIN",
        "qr_code": "QR_OR_BARCODE",
        "guarantee": "GUARANTEE_STAMP",
    }
    
    artifacts: list[dict[str, Any]] = []
    
    for item in items:
        if not isinstance(item, dict):
            continue
        
        # Only process ineligible items (failed QC)
        if item.get("eligible", False):
            continue
        
        asset_id = item.get("asset_id", "")
        findings = item.get("findings", {})
        
        if not isinstance(findings, dict):
            continue
        
        risk_flags = findings.get("risk_flags", [])
        if not isinstance(risk_flags, list):
            continue
        
        # Extract detected categories
        detected_categories = []
        for flag in risk_flags:
            if flag in category_map:
                detected_categories.append(category_map[flag])
        
        if detected_categories:
            artifacts.append({
                "asset_id": asset_id,
                "categories": detected_categories,
                "confidence": item.get("score", 0) / 100.0,
                "reason": item.get("reason", ""),
                "findings": findings,
            })
    
    return artifacts


def replace_images_in_resource_pack(
    resource_pack: dict[str, Any],
    cleaned_images: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace original images with cleaned versions in resource pack.
    
    Preserves original image paths for audit trail.
    
    Args:
        resource_pack: Original resource pack with media_assets
        cleaned_images: List of cleaned image results from ProductImageCleaner
        
    Returns:
        Updated resource pack with cleaned image paths
    """
    import copy
    
    cleaned_pack = copy.deepcopy(resource_pack)
    cleaned_by_id = {img["asset_id"]: img for img in cleaned_images}
    
    media_assets = cleaned_pack.get("media_assets", [])
    updated_assets = []
    
    for asset in media_assets:
        if not isinstance(asset, dict):
            updated_assets.append(asset)
            continue
        
        asset_id = asset.get("asset_id")
        
        if asset_id in cleaned_by_id:
            # Replace with cleaned version
            cleaned = cleaned_by_id[asset_id]
            updated_asset = dict(asset)
            updated_asset["local_path"] = cleaned["cleaned_path"]
            updated_asset["sha256"] = cleaned["clean_sha256"]
            updated_asset["original_path"] = asset.get("local_path")  # Preserve original
            updated_asset["cleaning_applied"] = True
            updated_asset["detected_artifacts"] = cleaned.get("detected_watermarks", [])
            updated_asset["detected_categories"] = cleaned.get("detected_categories", [])
            updated_assets.append(updated_asset)
        else:
            # Keep original (not in cleaned set)
            updated_assets.append(asset)
    
    cleaned_pack["media_assets"] = updated_assets
    return cleaned_pack


def extract_product_from_resource_pack(resource_pack: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized product metadata from resource pack for QC.
    
    Args:
        resource_pack: Resource pack containing product metadata
        
    Returns:
        Normalized product dict with brand, model, variant, display_name
    """
    # Try multiple locations for product metadata
    product = resource_pack.get("product", {})
    if not product:
        product = resource_pack.get("product_metadata", {})
    if not product:
        # Fallback: extract from top-level fields
        product = {
            "brand": resource_pack.get("brand", ""),
            "model": resource_pack.get("model", ""),
            "variant": resource_pack.get("variant"),
            "display_name": resource_pack.get("product_name") or resource_pack.get("name", ""),
            "verified_claims": resource_pack.get("key_features") or resource_pack.get("verified_claims", []),
        }
    
    return product
