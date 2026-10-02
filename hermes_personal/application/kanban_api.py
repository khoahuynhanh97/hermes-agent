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

from hermes_personal.product_video import ProductVideoWorkflowState
from hermes_personal.application.operator_handler import approve_and_advance_workflow


class ApprovalRequest(BaseModel):
    """Request body for approval actions."""
    workflow_id: str
    gate: str = Field(..., description="Gate name: brief|scene_plan|storyboard|final")
    action: str = Field(..., description="Action: approve|reject|rework")
    feedback: str = ""
    qc_authorization: dict[str, Any] | None = None
    qc_max_cost_usd: float | None = None
    render_provider_kind: str | None = None


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
        
        # Map state to column
        if state == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value:
            columns["awaiting_product_lock"].append(card)
        elif state == ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value:
            columns["awaiting_brief_approval"].append(card)
        elif state == ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL.value:
            columns["awaiting_scene_plan_approval"].append(card)
        elif state == ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value:
            columns["awaiting_storyboard_approval"].append(card)
        elif state in (
            ProductVideoWorkflowState.RENDERING.value,
            ProductVideoWorkflowState.CREATING_SCENE_PLAN.value,
            ProductVideoWorkflowState.CREATING_STORYBOARD.value,
        ):
            columns["in_production"].append(card)
        elif state == ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL.value:
            columns["awaiting_final_approval"].append(card)
        elif state == ProductVideoWorkflowState.COMPLETED.value:
            columns["completed"].append(card)
        elif state in (ProductVideoWorkflowState.FAILED.value, ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value):
            columns["error"].append(card)
    
    return columns


def _get_workflow_detail(connection: sqlite3.Connection, workflow_id: str) -> dict[str, Any]:
    """Return complete workflow state object."""
    row = connection.execute(
        "SELECT aggregate_json, version FROM workflow WHERE workflow_id = ?",
        (workflow_id,),
    ).fetchone()
    
    if not row:
        raise ValueError(f"Workflow {workflow_id} not found")
    
    agg = json.loads(row["aggregate_json"])
    
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
    
    return {
        "workflow_id": workflow_id,
        "version": row["version"],
        "state": agg.get("state"),
        "owner_user_id": agg.get("owner_user_id"),
        "created_at": agg.get("created_at"),
        "research_dossier": agg.get("research_dossier"),
        "creative_brief": agg.get("creative_brief"),
        "scene_plan": agg.get("scene_plan"),
        "storyboard": agg.get("storyboard"),
        "render_result": agg.get("render_result"),
        "export_result": agg.get("export_result"),
        "approval_history": approvals,
        "budget_ledger": budget_ledger,
        "qc_authorization": agg.get("qc_authorization"),
        "pending_approval_id": agg.get("pending_approval_id"),
        "pending_approval_gate": agg.get("pending_approval_gate"),
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
        if connection is None:
            raise HTTPException(status_code=500, detail="Database connection not configured")
        return connection
    
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
    
    return router
