"""FastAPI routes for durable Asset Projection API."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from hermes.application.asset_projection_service import AssetProjectionService
from hermes.runtime_layout import get_data_root, get_product_intelligence_data_root
from hermes.security.principal import current_principal

router = APIRouter()

def _approved_roots() -> list[Path]:
    roots = [get_data_root()]
    pi_root = get_product_intelligence_data_root()
    if pi_root is not None:
        roots.append(pi_root)
    return [root.resolve() for root in roots]


ALLOWED_MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm", ".wav", ".mp3"}


from fastapi import Depends
from hermes.channels.api.dependencies import get_authenticated_principal_context
from hermes.security.principal import PrincipalContext

def _owner_user_id() -> str:
    principal = current_principal.get()
    if principal:
        return principal.owner_user_id
    return "user"


def _service() -> AssetProjectionService:
    return AssetProjectionService.from_runtime()


def _validate_contained_media_path(file_path_str: str) -> Path:
    target = Path(file_path_str).expanduser().resolve()
    if target.suffix.lower() not in ALLOWED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=403, detail=f"FORBIDDEN: Extension {target.suffix} is not an allowed media extension")

    if not any(target == root or root in target.parents for root in _approved_roots()):
        raise HTTPException(status_code=403, detail="PATH_TRAVERSAL_REJECTED: Path outside approved media roots")
    return target


def _asset_or_missing(asset_id: str) -> Dict[str, Any] | None:
    return _service().get_asset(_owner_user_id(), asset_id)


@router.get("")
def list_assets(
    role: Optional[str] = Query(None, description="original | generated | storyboard"),
    product_id: Optional[str] = None,
    snapshot_id: Optional[str] = None,
    project_id: Optional[str] = None,
    source_domain: Optional[str] = None,
    principal: Optional[PrincipalContext] = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner_user_id = principal.owner_user_id if isinstance(principal, PrincipalContext) else _owner_user_id()
    assets = _service().list_assets(
        owner_user_id,
        role=role,
        product_id=product_id,
        snapshot_id=snapshot_id,
        project_id=project_id,
        source_domain=source_domain,
    )
    return {
        "status": "ok",
        "assets": [_service().public_asset(asset) for asset in assets],
        "total": len(assets),
    }


@router.get("/comparison")
def compare_assets(original_asset_id: str, generated_asset_id: str) -> Dict[str, Any]:
    owner = _owner_user_id()
    service = _service()
    original = service.get_asset(owner, original_asset_id)
    generated = service.get_asset(owner, generated_asset_id)
    return {
        "status": "ok",
        "original": service.public_asset(original) if original else None,
        "generated": service.public_asset(generated) if generated else None,
    }


@router.get("/{asset_id}")
def get_asset(asset_id: str) -> Dict[str, Any]:
    asset = _asset_or_missing(asset_id)
    if not asset:
        return {"status": "missing", "asset_id": asset_id, "reason": "Asset ID not found in projection"}
    return {"status": "ok", "asset": _service().public_asset(asset)}


@router.get("/{asset_id}/content", response_model=None)
def get_asset_content(asset_id: str):
    asset = _asset_or_missing(asset_id)
    if not asset:
        return {"status": "missing", "asset_id": asset_id, "reason": "Asset ID not found in projection"}
    target = _validate_contained_media_path(asset["local_path"])
    if not target.is_file():
        return {"status": "missing", "asset_id": asset_id, "reason": "Physical file does not exist on disk"}
    return FileResponse(target)


@router.post("/{asset_id}/open-file")
def open_asset_file(asset_id: str) -> Dict[str, Any]:
    asset = _asset_or_missing(asset_id)
    if not asset:
        return {"status": "missing", "asset_id": asset_id, "reason": "Asset ID not found in projection"}

    target = _validate_contained_media_path(asset["local_path"])
    if not target.is_file():
        return {"status": "missing", "asset_id": asset_id, "reason": "Physical file does not exist on disk"}
    return {"status": "ok", "asset_id": asset_id, "action": "open_file", "display_name": target.name}


@router.post("/{asset_id}/open-folder")
def open_asset_folder(asset_id: str) -> Dict[str, Any]:
    asset = _asset_or_missing(asset_id)
    if not asset:
        return {"status": "missing", "asset_id": asset_id, "reason": "Asset ID not found in projection"}

    target = _validate_contained_media_path(asset["local_path"])
    folder = target.parent
    if not folder.is_dir():
        return {"status": "missing", "asset_id": asset_id, "reason": "Containing directory does not exist on disk"}
    return {"status": "ok", "asset_id": asset_id, "action": "open_folder", "display_name": folder.name}
