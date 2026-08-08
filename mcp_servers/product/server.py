from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from hermes.adapters.affiliate.shopee_csv import ShopeeAffiliateCsvSource
from hermes.adapters.sqlite.affiliate_research_repository import (
    SQLiteAffiliateResearchRepository,
)
from hermes.application.affiliate_catalog_service import AffiliateCatalogService
from hermes.application.affiliate_review_service import AffiliateReviewService, PackageNotFound
from hermes.db import Database


mcp = FastMCP("hermes-product")


def product_import_candidates(
    owner_user_id: str,
    csv_path: str,
    run_id: str,
) -> dict[str, Any]:
    """Import an authorized CSV through the existing catalog application service."""
    owner_user_id, run_id = _required_ids(owner_user_id, run_id)
    import_path = _resolve_import_path(csv_path)
    repository = _repository()
    repository.create_run(
        run_id,
        owner_user_id,
        idempotency_key=f"hermes-product:{run_id}",
    )
    summary = AffiliateCatalogService(repository).import_candidates(
        ShopeeAffiliateCsvSource(import_path),
        owner_user_id=owner_user_id,
        run_id=run_id,
        snapshot_date=datetime.now(timezone.utc).date().isoformat(),
    )
    return {
        "ok": True,
        "run_id": run_id,
        **asdict(summary),
    }


def product_score_shortlist(
    owner_user_id: str,
    run_id: str,
    minimum: int = 15,
    maximum: int = 25,
) -> dict[str, Any]:
    """Score products already attached to a run and persist the shortlist."""
    owner_user_id, run_id = _required_ids(owner_user_id, run_id)
    repository = _repository()
    run = repository.get_run(run_id, owner_user_id)
    shortlist = AffiliateCatalogService(repository).score_and_shortlist(
        owner_user_id=owner_user_id,
        run_id=run_id,
        minimum=minimum,
        maximum=maximum,
    )
    counters = dict(run.get("counters") or {})
    counters["shortlisted"] = len(shortlist)
    repository.finish_run(run_id, counters)
    return {
        "ok": True,
        "run_id": run_id,
        "shortlist": [_ranked_product_payload(item) for item in shortlist],
    }


def product_get_run(owner_user_id: str, run_id: str) -> dict[str, Any]:
    """Return one owned product research run and its persisted counters."""
    owner_user_id, run_id = _required_ids(owner_user_id, run_id)
    repository = _repository()
    products = repository.list_run_products(run_id, owner_user_id)
    return {
        "ok": True,
        **repository.get_run(run_id, owner_user_id),
        "products": products,
        "shortlist": [product for product in products if product["shortlisted"]],
    }


def product_list_packages(
    owner_user_id: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """List owned content packages, optionally limited to a product run."""
    owner_user_id = owner_user_id.strip()
    if not owner_user_id:
        raise ValueError("owner_user_id is required")
    if run_id is not None:
        run_id = run_id.strip()
        if not run_id:
            raise ValueError("run_id must not be empty when provided")
    packages = _repository().list_packages(owner_user_id, run_id=run_id)
    return {
        "ok": True,
        "run_id": run_id,
        "packages": [_package_payload(package) for package in packages],
    }


def product_approve_package(
    owner_user_id: str,
    package_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Approve one owner-scoped affiliate content package."""
    return _review_package(owner_user_id, package_id, "approve", reason)


def product_reject_package(
    owner_user_id: str,
    package_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Reject one owner-scoped affiliate content package."""
    return _review_package(owner_user_id, package_id, "reject", reason)


def product_request_package_revision(
    owner_user_id: str,
    package_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Request a revision for one owner-scoped affiliate content package."""
    return _review_package(owner_user_id, package_id, "revise", reason)


def _review_package(
    owner_user_id: str,
    package_id: str,
    action: str,
    reason: str,
) -> dict[str, Any]:
    owner_user_id = _required_review_id(owner_user_id, "owner_user_id")
    package_id = _required_review_id(package_id, "package_id")
    before = _repository().get_package(package_id, owner_user_id)
    if before is None:
        raise ValueError("PACKAGE_NOT_FOUND")
    try:
        package = AffiliateReviewService(_repository()).apply(
            package_id, owner_user_id, action, reason.strip()
        )
    except PackageNotFound as error:
        raise ValueError("PACKAGE_NOT_FOUND") from error
    return {
        "ok": True,
        "changed": package.status is not before.status,
        "action": action,
        "owner_user_id": owner_user_id,
        "package": _package_payload(package),
    }


def _required_review_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _repository() -> SQLiteAffiliateResearchRepository:
    database_path = _database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteAffiliateResearchRepository(Database(database_path))


def _database_path() -> Path:
    configured = os.environ.get("HERMES_P1_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(tempfile.gettempdir()) / "hermes-product" / "hermes.db").resolve()


def _resolve_import_path(csv_path: str) -> Path:
    configured_root = os.environ.get("AFFILIATE_IMPORT_DIR", "").strip()
    if not configured_root:
        raise ValueError("AFFILIATE_IMPORT_DIR must be configured for the Product MCP")
    root = Path(configured_root).expanduser().resolve()
    candidate = Path(csv_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("csv_path must resolve inside AFFILIATE_IMPORT_DIR") from error
    if candidate.suffix.lower() != ".csv":
        raise ValueError("csv_path must point to a CSV file")
    if not candidate.is_file():
        raise ValueError("csv_path must point to an existing file")
    return candidate


def _required_ids(owner_user_id: str, run_id: str) -> tuple[str, str]:
    owner_user_id = owner_user_id.strip()
    run_id = run_id.strip()
    if not owner_user_id:
        raise ValueError("owner_user_id is required")
    if not run_id:
        raise ValueError("run_id is required")
    return owner_user_id, run_id


def _ranked_product_payload(item: Any) -> dict[str, Any]:
    return {
        "product_id": item.product.id,
        "external_product_id": item.product.external_product_id,
        "name": item.product.name,
        "category": item.product.category,
        "score": item.score.total,
        "confidence": item.score.confidence,
        "reason": item.score.reason,
        "evidence_ids": list(item.score.evidence_ids),
        "snapshot_timestamps": list(item.score.snapshot_timestamps),
    }


def _package_payload(package: Any) -> dict[str, Any]:
    payload = asdict(package)
    payload["status"] = package.status.value
    return payload


for _tool in (
    product_import_candidates,
    product_score_shortlist,
    product_get_run,
    product_list_packages,
    product_approve_package,
    product_reject_package,
    product_request_package_revision,
):
    mcp.tool()(_tool)


if __name__ == "__main__":
    mcp.run()
