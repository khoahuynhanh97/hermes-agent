"""Candidate products & Product Discovery REST API for Hermes Product Video.

Provides endpoints to inspect scouted daily products, start video workflows,
serve raw assets, and render the Product Video Operator Console.
"""
from __future__ import annotations

import mimetypes
import os
import re
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from hermes_constants import get_hermes_home
from hermes_personal.application.operator_handler import approve_and_advance_workflow
from hermes_personal.product_video.automation.importer import DEFAULT_EXCHANGE_INBOX
from hermes_personal.product_video.automation.repository import DailyImportRepository
from hermes_personal.product_video.operator_console import render_operator_console_html
from hermes_personal.storage.sqlite import connect


def create_candidate_router(connection: sqlite3.Connection | None = None) -> APIRouter:
    """Create Candidate and Product Discovery API router."""
    from hermes_personal.product_video.candidate_service import DailyCandidateService

    router = APIRouter(tags=["product-discovery"])

    def get_connection() -> sqlite3.Connection:
        if connection is not None:
            return connection
        try:
            db_path = get_hermes_home() / "hermes_personal.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return connect(db_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Database connection error: {exc}")

    # ─────────────────────────────────────────────────────────────
    # Web HTML Console Page
    # ─────────────────────────────────────────────────────────────
    @router.get("/products", response_class=HTMLResponse)
    @router.get("/console", response_class=HTMLResponse)
    @router.get("/personal/product-video", response_class=HTMLResponse)
    @router.get("/api/personal/product-video/console", response_class=HTMLResponse)
    def get_product_discovery_console(
        target_date: str | None = Query(None),
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> HTMLResponse:
        """Serve the Product Discovery & Daily Video Operator Console."""
        service = DailyCandidateService(conn)
        parsed_date = date.fromisoformat(target_date) if target_date else None
        initial_candidates = []
        try:
            candidates = service.get_candidates(target_date=parsed_date)
            initial_candidates = [c.to_dict() for c in candidates]
        except Exception:
            initial_candidates = []

        return HTMLResponse(content=render_operator_console_html(initial_candidates))

    # ─────────────────────────────────────────────────────────────
    # Candidate Data Endpoints
    # ─────────────────────────────────────────────────────────────
    @router.get("/api/personal/product-video/candidates")
    def get_product_video_candidates(
        target_date: str | None = Query(None),
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> JSONResponse:
        """Return scouted candidate products for a given date."""
        service = DailyCandidateService(conn)
        parsed_date = date.fromisoformat(target_date) if target_date else None
        try:
            candidates = service.get_candidates(target_date=parsed_date)
            return JSONResponse(
                content={
                    "ok": True,
                    "source_date": candidates[0].source_date if candidates else (target_date or ""),
                    "candidates": [c.to_dict() for c in candidates],
                }
            )
        except Exception as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})

    @router.post("/api/personal/product-video/start-batch")
    async def start_product_video_batch(
        request: Request,
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> JSONResponse:
        """Trigger video production workflow for selected products or auto-start top N."""
        try:
            body = await request.json()
        except Exception:
            body = {}

        service = DailyCandidateService(conn)
        minimum_daily = int(body.get("minimum_daily") or 0)
        target_date = (
            date.fromisoformat(body["target_date"])
            if body.get("target_date")
            else (date.today() if minimum_daily else None)
        )
        owner = str(body.get("owner_id") or "local-owner")

        try:
            if minimum_daily < 0 or minimum_daily > 5:
                raise ValueError("minimum_daily must be between 0 and 5")
            if body.get("auto"):
                limit = int(body.get("limit") or 5)
                if minimum_daily > limit:
                    raise ValueError("minimum_daily cannot exceed limit")
                res = service.start_auto(limit=limit, owner_user_id=owner, target_date=target_date)
            else:
                keys = list(body.get("product_keys") or [])
                res = service.start_selection(product_keys=keys, owner_user_id=owner, target_date=target_date)

            started_list = [asdict(s) if is_dataclass(s) else dict(s) for s in res.started]
            skipped_list = [asdict(s) if is_dataclass(s) else dict(s) for s in res.skipped]
            daily_started_total = None
            if minimum_daily and target_date is not None:
                rows = DailyImportRepository(conn).get_all_for_date(target_date.isoformat())
                daily_started_total = sum(row["status"] == "started" for row in rows.values())
            shortfall = daily_started_total is not None and daily_started_total < minimum_daily

            return JSONResponse(
                status_code=409 if res.has_errors or shortfall else 200,
                content={
                    "ok": not (res.has_errors or shortfall),
                    "started": started_list,
                    "skipped": skipped_list,
                    "started_workflows": [s["workflow_id"] for s in started_list],
                    "daily_started_total": daily_started_total,
                    "minimum_daily": minimum_daily,
                    "error": "INSUFFICIENT_DAILY_PRODUCTS"
                    if shortfall
                    else ("BATCH_START_FAILED" if res.has_errors else None),
                },
            )
        except Exception as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})

    @router.post("/api/personal/product-video/approve-lock")
    async def approve_product_lock(
        request: Request,
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> JSONResponse:
        """Approve Product Lock for a candidate workflow."""
        try:
            body = await request.json()
        except Exception:
            body = {}

        target_id = str(body.get("target_id") or body.get("approval_id") or "")
        if not target_id:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "target_id or approval_id is required"}
            )
        owner = str(body.get("owner_id") or "local-owner")

        try:
            res = approve_and_advance_workflow(connection=conn, target_id=target_id, owner_user_id=owner)
            return JSONResponse(content={"ok": True, "result": res})
        except Exception as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})

    @router.get("/api/personal/product-video/assets/{source_date}/{source_batch_id}/{asset_path:path}")
    def get_product_video_asset(
        source_date: str,
        source_batch_id: str,
        asset_path: str,
    ) -> Response:
        """Serve raw image or video asset from product exchange inbox."""
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", source_date):
            return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid date format"})
        if not re.match(r"^[a-zA-Z0-9_\-]+$", source_batch_id):
            return JSONResponse(status_code=400, content={"ok": False, "error": "Invalid batch_id format"})

        env_inbox = os.environ.get("HERMES_EXCHANGE_INBOX")
        inbox_root = Path(env_inbox).resolve() if env_inbox else DEFAULT_EXCHANGE_INBOX.resolve()
        batch_dir = (inbox_root / source_date / source_batch_id).resolve()

        try:
            batch_dir.relative_to(inbox_root)
        except ValueError:
            return JSONResponse(status_code=403, content={"ok": False, "error": "Access denied"})

        if not batch_dir.is_dir():
            return JSONResponse(status_code=404, content={"ok": False, "error": "Batch directory not found"})

        target_file = (batch_dir / asset_path).resolve()
        try:
            target_file.relative_to(batch_dir)
        except ValueError:
            return JSONResponse(
                status_code=403, content={"ok": False, "error": "Access denied: path traversal detected"}
            )

        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm"}
        if target_file.suffix.lower() not in allowed_extensions:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Unsupported media asset extension"}
            )

        if not target_file.is_file():
            return JSONResponse(status_code=404, content={"ok": False, "error": "Asset not found"})

        mime_type, _ = mimetypes.guess_type(str(target_file))
        return FileResponse(target_file, media_type=mime_type or "application/octet-stream")

    return router
