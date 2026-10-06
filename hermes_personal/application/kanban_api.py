"""Kanban & Operator REST API for Product Video workflows.

Provides structured endpoints for visual Kanban Board interface and HITL gate operations.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hermes_personal.product_video.schemas import VideoWorkflowAggregate
from hermes_personal.product_video import ProductVideoWorkflowState
from hermes_personal.application.operator_handler import (
    approve_and_advance_workflow,
    resume_video_scene_after_qc_failure,
)
from hermes_personal.integrations.video_factory.scene_renderer import SceneRenderOperationStore


class ApprovalRequest(BaseModel):
    """Request body for approval actions."""
    workflow_id: str
    gate: str = Field(..., description="Gate name: brief|scene_plan|storyboard|final")
    action: str = Field(..., description="Action: approve|reject|rework")
    feedback: str = ""
    qc_authorization: dict[str, Any] | None = None
    qc_max_cost_usd: float | None = None
    render_provider_kind: str | None = None


class SceneReRenderRequest(BaseModel):
    """Request body to trigger re-rendering of a single scene."""
    workflow_id: str
    scene_order: int = Field(..., ge=1, le=10, description="1-indexed scene order (e.g. 1, 2, 3, 4)")
    provider_kind: str | None = Field(None, description="Optional provider kind (e.g. google_flow, vertex_veo)")
    custom_prompt: str | None = Field(None, description="Optional prompt override for this scene retry")


def _get_kanban_cards(connection: sqlite3.Connection, owner_user_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Query workflows grouped by Kanban column (state)."""
    query = """
    SELECT 
        workflow_id,
        aggregate_json,
        version
    FROM workflow
    WHERE 1=1
    """
    params = []
    
    if owner_user_id:
        query += " AND json_extract(aggregate_json, '$.owner_user_id') = ?"
        params.append(owner_user_id)
    
    query += " ORDER BY json_extract(aggregate_json, '$.created_at') DESC LIMIT 100"
    
    rows = connection.execute(query, params).fetchall()
    
    columns = {
        "awaiting_product_lock": [],
        "awaiting_brief_approval": [],
        "awaiting_scene_plan_approval": [],
        "awaiting_storyboard_approval": [],
        "in_production": [],
        "awaiting_final_approval": [],
        "completed": [],
        "error": [],
    }
    
    for row in rows:
        agg = json.loads(row["aggregate_json"])
        state = agg.get("state", "")
        workflow_id = row["workflow_id"]
        
        card = {
            "workflow_id": workflow_id,
            "product_name": agg.get("product_name", agg.get("source_context", {}).get("model", "Unknown")),
            "created_at": agg.get("created_at", ""),
            "state": state,
            "version": row["version"],
        }
        
        # Add thumbnail if available
        latest_artifact = agg.get("latest_artifact", {})
        if isinstance(latest_artifact, dict):
            thumbnail = (
                latest_artifact.get("thumbnail_url")
                or (latest_artifact.get("generated_keyframes", [{}])[0].get("image_url") if latest_artifact.get("generated_keyframes") else None)
                or latest_artifact.get("video_url")
            )
            if thumbnail:
                card["thumbnail_url"] = thumbnail
        
        # Add estimated cost if available
        qc_auth = agg.get("qc_authorization", {})
        if isinstance(qc_auth, dict):
            card["estimated_cost"] = qc_auth.get("workflow_max_cost_usd", qc_auth.get("max_cost_usd"))
        
        # Add target duration if available
        for artifact_key in ("creative_brief", "scene_plan", "latest_artifact"):
            artifact = agg.get(artifact_key)
            if isinstance(artifact, dict) and artifact.get("target_duration"):
                card["target_duration"] = artifact["target_duration"]
                break

        # Robust state to column mapping
        s = str(state or "").strip().lower()
        if s in ("awaitingproductlock", "awaiting_product_lock"):
            columns["awaiting_product_lock"].append(card)
        elif s in ("awaitingbriefapproval", "awaiting_brief_approval"):
            columns["awaiting_brief_approval"].append(card)
        elif s in ("awaitingsceneapproval", "awaiting_scene_approval", "awaitingsceneplanapproval", "awaiting_scene_plan_approval"):
            columns["awaiting_scene_plan_approval"].append(card)
        elif s in ("awaitingstoryboardapproval", "awaiting_storyboard_approval"):
            columns["awaiting_storyboard_approval"].append(card)
        elif s in ("awaitingfinalapproval", "awaiting_final_approval"):
            columns["awaiting_final_approval"].append(card)
        elif s in ("completed", "done", "success"):
            columns["completed"].append(card)
        elif s in ("waitingforoperator", "waiting_for_operator", "error", "failed"):
            columns["error"].append(card)
        else:
            # All in-progress active pipeline states (researching, building_resource_pack, rendering, exporting, etc.)
            columns["in_production"].append(card)
    
    return columns


def _get_workflow_detail(connection: sqlite3.Connection, workflow_id: str) -> dict[str, Any]:
    """Return complete workflow state object."""
    row = connection.execute(
        "SELECT aggregate_json, version FROM workflow WHERE workflow_id = ?",
        (workflow_id,),
    ).fetchone()
    
    if not row:
        raise ValueError(f"Workflow {workflow_id} not found")
    
    # Use Pydantic model for validation and clean serialization
    agg_dict = json.loads(row["aggregate_json"])
    agg = VideoWorkflowAggregate.model_validate(agg_dict)
    
    # Fetch approval history (table may not exist in all environments)
    approvals = []
    try:
        approval_rows = connection.execute(
            """
            SELECT request_id, status, payload_json, created_at, updated_at
            FROM approval_request
            WHERE json_extract(payload_json, '$.workflow_id') = ?
            ORDER BY created_at DESC
            """,
            (workflow_id,),
        ).fetchall()
        
        approvals = [
            {
                "request_id": r["request_id"],
                "status": r["status"],
                "gate": json.loads(r["payload_json"]).get("gate"),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in approval_rows
        ]
    except sqlite3.OperationalError:
        pass
    
    # Fetch QC reports for the scorecard
    qc_reports = []
    try:
        qc_rows = connection.execute(
            """
            SELECT report_id, stage, artifact_digest, score, verdict,
                   findings_json, evaluator_name, created_at
            FROM product_video_qc_reports
            WHERE workflow_id = ?
            ORDER BY created_at ASC
            """,
            (workflow_id,),
        ).fetchall()
        qc_reports = [
            {
                "report_id": r["report_id"],
                "stage": r["stage"],
                "artifact_digest": r["artifact_digest"],
                "score": r["score"],
                "verdict": r["verdict"],
                "findings": json.loads(r["findings_json"] or "{}"),
                "evaluator_name": r["evaluator_name"],
                "created_at": r["created_at"],
            }
            for r in qc_rows
        ]
    except sqlite3.OperationalError:
        pass

    # Fetch cost ledger
    budget_ledger = []
    try:
        budget_rows = connection.execute(
            """
            SELECT reservation_id, capability_id, amount, currency, state, created_at
            FROM budget_reservation
            WHERE scope_id = ?
            ORDER BY created_at DESC
            """,
            (workflow_id,),
        ).fetchall()
        
        budget_ledger = [
            {
                "reservation_id": r["reservation_id"],
                "capability_id": r["capability_id"],
                "amount": r["amount"],
                "currency": r["currency"],
                "state": r["state"],
                "created_at": r["created_at"],
            }
            for r in budget_rows
        ]
    except sqlite3.OperationalError:
        pass
    
    # Fetch scene operations (rendered clips status per scene)
    scene_operations = []
    try:
        render_result = agg_dict.get("render_result") or {}
        batch_id = render_result.get("render_id") or ""
        if batch_id:
            scene_rows = connection.execute(
                """
                SELECT operation_id, scene_id, scene_order, attempt, status,
                       output_path, provider_kind, updated_at
                FROM video_factory_scene_operation
                WHERE render_batch_id = ?
                ORDER BY scene_order ASC, attempt DESC
                """,
                (batch_id,),
            ).fetchall()
            seen_scenes: set[int] = set()
            for r in scene_rows:
                order = r["scene_order"]
                if order not in seen_scenes:
                    seen_scenes.add(order)
                    scene_operations.append({
                        "operation_id": r["operation_id"],
                        "scene_id": r["scene_id"],
                        "scene_order": order,
                        "attempt": r["attempt"],
                        "status": r["status"],
                        "output_path": r["output_path"],
                        "provider_kind": r["provider_kind"],
                        "updated_at": r["updated_at"],
                    })
    except sqlite3.OperationalError:
        pass
    
    # Return the validated model as a dictionary
    return agg.model_dump(
        include={
            "workflow_id", "state", "owner_user_id", "created_at",
            "research_dossier", "creative_brief", "scene_plan", "storyboard",
            "render_result", "export_result", "qc_authorization",
            "pending_approval_id", "pending_approval_gate"
        }
    ) | {
        "version": row["version"],
        "qc_reports": qc_reports,
        "approval_history": approvals,
        "budget_ledger": budget_ledger,
        "scene_operations": scene_operations,
    }



async def _event_stream(connection: sqlite3.Connection, owner_user_id: str | None = None) -> AsyncGenerator[str, None]:
    """SSE stream for live workflow state changes."""
    import asyncio
    
    last_cursor = 0
    
    while True:
        # Poll for new events
        query = "SELECT cursor, event_id FROM owner_event_cursor WHERE cursor > ?"
        params = [last_cursor]
        
        if owner_user_id:
            query += " AND owner_user_id = ?"
            params.append(owner_user_id)
        
        query += " ORDER BY cursor ASC LIMIT 10"
        
        rows = connection.execute(query, params).fetchall()
        
        for row in rows:
            last_cursor = row["cursor"]
            event_id = row["event_id"]
            
            # Fetch event payload
            event_row = connection.execute(
                "SELECT payload_json FROM turn_event WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            
            if event_row:
                yield f"data: {event_row['payload_json']}\n\n"
        
        await asyncio.sleep(1.0)


def create_kanban_router(connection: sqlite3.Connection | None = None) -> APIRouter:
    """Create Kanban & Operator API router."""
    router = APIRouter(prefix="/api/operator", tags=["operator"])
    
    def get_connection() -> sqlite3.Connection:
        if connection is not None:
            return connection
        try:
            from hermes_constants import get_hermes_home
            from hermes_personal.storage.sqlite import connect
            db_path = get_hermes_home() / "hermes_personal.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return connect(db_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Database connection error: {exc}")

    
    @router.get("/kanban")
    async def get_kanban(
        owner_user_id: str | None = Query(None),
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, Any]:
        """Get Kanban board with workflows grouped by state column."""
        try:
            columns = _get_kanban_cards(conn, owner_user_id)
            return {"columns": columns, "timestamp": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/workflow/{workflow_id}")
    async def get_workflow_detail(
        workflow_id: str,
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, Any]:
        """Get complete workflow state object."""
        try:
            return _get_workflow_detail(conn, workflow_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post("/approve")
    async def approve_workflow(
        request: ApprovalRequest,
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, Any]:
        """Approve, reject, or request rework on a workflow gate."""
        if request.action != "approve":
            raise HTTPException(status_code=400, detail="Only 'approve' action is currently supported")
        
        try:
            payload = {}
            if request.qc_authorization:
                payload["qc_authorization"] = request.qc_authorization
            if request.qc_max_cost_usd is not None:
                payload["qc_max_cost_usd"] = request.qc_max_cost_usd
            if request.render_provider_kind:
                payload["render_provider_kind"] = request.render_provider_kind
            
            result = approve_and_advance_workflow(
                connection=conn,
                target_id=request.workflow_id,
                owner_user_id="local-owner",  # TODO: Extract from auth context
                payload=payload if payload else None,
            )
            
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/stream")
    async def stream_events(
        owner_user_id: str | None = Query(None),
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> StreamingResponse:
        """SSE stream for real-time workflow state changes."""
        return StreamingResponse(
            _event_stream(conn, owner_user_id),
            media_type="text/event-stream",
        )
    
    @router.post("/rework")
    async def rework_workflow(
        request: ApprovalRequest,
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, Any]:
        """Request rework on a workflow gate."""
        if request.action != "rework":
            raise HTTPException(status_code=400, detail="Only 'rework' action is supported here")
        if not request.feedback:
            raise HTTPException(status_code=400, detail="Feedback is required for rework")
        
        # TODO: Implement actual rework logic in operator_handler
        return {"status": "rework_requested", "workflow_id": request.workflow_id}

    @router.post("/workflow/{workflow_id}/scene/re-render")
    async def re_render_scene(
        workflow_id: str,
        request: SceneReRenderRequest,
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, Any]:
        """Granular scene re-render endpoint. Rerenders a single scene and resumes batch."""
        if workflow_id != request.workflow_id:
            raise HTTPException(status_code=400, detail="Mismatched workflow_id in path and body")
        
        try:
            scene_store = SceneRenderOperationStore(conn)
            result = resume_video_scene_after_qc_failure(
                connection=conn,
                scene_store=scene_store,
                workflow_id=workflow_id,
                owner_user_id="local-owner",
                scene_order=request.scene_order,
                provider_kind=request.provider_kind,
            )
            return {"ok": True, "result": result}
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/product/{product_key}/workflows")
    async def get_product_workflows(
        product_key: str,
        conn: sqlite3.Connection = Depends(get_connection),
    ) -> dict[str, Any]:
        """List all video workflows associated with a product (up to 10 videos)."""
        try:
            rows = conn.execute(
                """
                SELECT workflow_id, aggregate_json, version
                FROM workflow
                WHERE json_extract(aggregate_json, '$.source_context.product_key') = ?
                   OR workflow_id LIKE ?
                ORDER BY json_extract(aggregate_json, '$.created_at') ASC
                LIMIT 10
                """,
                (product_key, f"%{product_key}%"),
            ).fetchall()

            workflows = []
            for r in rows:
                agg = json.loads(r["aggregate_json"])
                workflows.append({
                    "workflow_id": r["workflow_id"],
                    "state": agg.get("state"),
                    "version": r["version"],
                    "created_at": agg.get("created_at"),
                    "video_url": (agg.get("latest_artifact") or {}).get("video_url") or (agg.get("export_result") or {}).get("video_path"),
                    "thumbnail_url": (agg.get("latest_artifact") or {}).get("thumbnail_url"),
                })
            return {"ok": True, "product_key": product_key, "workflows": workflows}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router
