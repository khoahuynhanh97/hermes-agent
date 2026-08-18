"""FastAPI routes for Product Research Studio."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from hermes.application.asset_projection_service import AssetProjectionService
from hermes.application.product_research_intent import ProductResearchIntent
from hermes.security.principal import current_principal

router = APIRouter()


def _owner_user_id() -> str:
    principal = current_principal.get()
    if principal:
        return principal.owner_user_id
    return "user"


def _service() -> AssetProjectionService:
    return AssetProjectionService.from_runtime()


def build_product_research_workflow():
    from hermes.adapters.google.sheets_projection import DisabledSheetsProjection, GoogleSheetsProjection
    from hermes.adapters.local.sheet_projection import LocalSheetProjection
    from hermes.adapters.model.affiliate_content_gateway import AffiliateContentGateway
    from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
    from hermes.affiliate_config import load_affiliate_research_settings
    from hermes.application.affiliate_catalog_service import AffiliateCatalogService
    from hermes.application.affiliate_content_service import AffiliateContentService
    from hermes.application.product_research_script_workflow import ProductResearchScriptWorkflow
    from hermes.application.product_source_selector import ProductSourceSelector
    from hermes.db import Database
    from hermes.llm import HermesLLMGateway

    settings = load_affiliate_research_settings()
    repository = SQLiteAffiliateResearchRepository(Database())
    google_projection = (
        GoogleSheetsProjection.from_environment(repository)
        if settings.google_sheets_enabled
        else DisabledSheetsProjection()
    )
    return ProductResearchScriptWorkflow(
        repository=repository,
        catalog_service=AffiliateCatalogService(repository),
        content_service=AffiliateContentService(repository, AffiliateContentGateway(HermesLLMGateway())),
        source_selector=ProductSourceSelector(settings),
        local_projection=LocalSheetProjection(repository, settings.local_sheet_output_dir),
        google_projection=google_projection,
        shortlist_limit=settings.shortlist_limit,
    )


class ProductResearchRunRequest(BaseModel):
    message: str = Field(..., min_length=1)


@router.get("")
def list_products(query: Optional[str] = None, limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, Any]:
    products = _service().list_products(_owner_user_id(), query=query, limit=limit)
    return {"status": "ok", "products": products, "total": len(products)}


@router.get("/runs")
def list_runs(status: Optional[str] = None, limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, Any]:
    return {"status": "ok", "runs": _service().list_runs(_owner_user_id(), status=status, limit=limit)}


@router.post("/research/run")
def run_product_research(body: ProductResearchRunRequest) -> Dict[str, Any]:
    try:
        intent = ProductResearchIntent.from_message(_owner_user_id(), body.message)
        result = build_product_research_workflow().run(intent)
        return {"status": "ok", "intent": intent.to_payload(), "result": result.to_payload()}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/{product_id}")
def get_product_detail(product_id: str) -> Dict[str, Any]:
    service = _service()
    detail = service.get_product(_owner_user_id(), product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    detail["assets"] = [service.public_asset(asset) for asset in detail.get("assets", [])]
    detail["generated_media"] = [
        service.public_asset(asset) for asset in detail.get("generated_media", [])
    ]
    return {"status": "ok", **detail}


@router.get("/{product_id}/assets")
def get_product_assets(product_id: str) -> Dict[str, Any]:
    service = _service()
    assets = service.list_assets(_owner_user_id(), product_id=product_id)
    return {
        "status": "ok",
        "assets": [service.public_asset(asset) for asset in assets],
        "total": len(assets),
    }
