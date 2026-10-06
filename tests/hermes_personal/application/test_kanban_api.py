"""Tests for Kanban & Operator REST API."""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hermes_personal.application.kanban_api import create_kanban_router
from hermes_personal.product_video import ProductVideoWorkflowState
from hermes_personal.product_video.schemas import VideoWorkflowAggregate, ResearchDossierSchema, CreativeBriefSchema
from hermes_personal.storage.sqlite import connect


@pytest.fixture
def db_connection():
    """Create a temporary database connection for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = connect(db_path)
        yield conn
        conn.close()


@pytest.fixture
def test_client(db_connection):
    """Create FastAPI test client with Kanban router."""
    router = create_kanban_router(connection=db_connection)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _create_test_workflow(conn: sqlite3.Connection, workflow_id: str, state: str, owner_user_id: str = "test-owner") -> None:
    """Helper to create a test workflow."""
    aggregate = {
        "workflow_id": workflow_id,
        "owner_user_id": owner_user_id,
        "state": state,
        "product_name": f"Test Product {workflow_id}",
        "created_at": "2026-10-01T00:00:00Z",
        "project_id": f"proj_{workflow_id}",
    }
    
    conn.execute(
        "INSERT INTO workflow (workflow_id, aggregate_json, version) VALUES (?, ?, ?)",
        (workflow_id, json.dumps(aggregate), 1),
    )
    conn.commit()


def test_get_kanban_returns_columns(test_client, db_connection):
    """Test GET /api/operator/kanban returns correct column structure."""
    # Create test workflows in different states
    _create_test_workflow(db_connection, "wf_001", ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value)
    _create_test_workflow(db_connection, "wf_002", ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value)
    _create_test_workflow(db_connection, "wf_003", ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value)
    _create_test_workflow(db_connection, "wf_004", ProductVideoWorkflowState.RENDERING.value)
    _create_test_workflow(db_connection, "wf_005", ProductVideoWorkflowState.COMPLETED.value)
    
    response = test_client.get("/api/operator/kanban")
    
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data
    assert "timestamp" in data
    
    columns = data["columns"]
    assert "awaiting_product_lock" in columns
    assert "awaiting_brief_approval" in columns
    assert "awaiting_storyboard_approval" in columns
    assert "in_production" in columns
    assert "completed" in columns
    
    # Verify workflows are in correct columns
    assert len(columns["awaiting_product_lock"]) == 1
    assert columns["awaiting_product_lock"][0]["workflow_id"] == "wf_001"
    
    assert len(columns["awaiting_brief_approval"]) == 1
    assert columns["awaiting_brief_approval"][0]["workflow_id"] == "wf_002"
    
    assert len(columns["awaiting_storyboard_approval"]) == 1
    assert columns["awaiting_storyboard_approval"][0]["workflow_id"] == "wf_003"
    
    assert len(columns["in_production"]) == 1
    assert columns["in_production"][0]["workflow_id"] == "wf_004"
    
    assert len(columns["completed"]) == 1
    assert columns["completed"][0]["workflow_id"] == "wf_005"


def test_get_kanban_filters_by_owner(test_client, db_connection):
    """Test GET /api/operator/kanban filters by owner_user_id."""
    _create_test_workflow(db_connection, "wf_owner1", ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value, "owner1")
    _create_test_workflow(db_connection, "wf_owner2", ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value, "owner2")
    
    response = test_client.get("/api/operator/kanban?owner_user_id=owner1")
    
    assert response.status_code == 200
    data = response.json()
    columns = data["columns"]
    
    assert len(columns["awaiting_brief_approval"]) == 1
    assert columns["awaiting_brief_approval"][0]["workflow_id"] == "wf_owner1"


def test_get_workflow_detail_returns_complete_state(test_client, db_connection):
    """Test GET /api/operator/workflow/{id} returns complete workflow state."""
    workflow_id = "wf_detail_test"
    # Create a VideoWorkflowAggregate instance
    agg = VideoWorkflowAggregate(
        workflow_id=workflow_id,
        owner_user_id="test-owner",
        state=ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value,
        created_at="2026-10-01T00:00:00Z",
        project_id="proj-1",
        research_dossier=ResearchDossierSchema(
            product_id="prod-1",
            brand="TestBrand",
            model="TestModel",
            product_name="Test Product",
            verified_claims=["claim1", "claim2"],
            images=[]
        ),
        creative_brief=CreativeBriefSchema(
            brief_id="brief_001",
            hook="Test hook",
            target_audience="Testers",
            target_duration=30,
            script=[{"segment": "intro"}]
        ),
        qc_authorization={"max_cost_usd": 50.0},
    )
    # Convert to dict for insertion
    aggregate_dict = agg.model_dump()
    # Ensure we have a version (we'll set to 2)
    version = 2
    
    db_connection.execute(
        "INSERT INTO workflow (workflow_id, aggregate_json, version) VALUES (?, ?, ?)",
        (workflow_id, json.dumps(aggregate_dict), version),
    )
    db_connection.commit()
    
    response = test_client.get(f"/api/operator/workflow/{workflow_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["workflow_id"] == workflow_id
    assert data["version"] == 2
    assert data["state"] == ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value
    assert data["owner_user_id"] == "test-owner"
    assert data["research_dossier"]["product_name"] == "Test Product"
    assert data["creative_brief"]["hook"] == "Test hook"
    assert data["qc_authorization"]["max_cost_usd"] == 50.0
    assert data["pending_approval_id"] is None  # We didn't set it in the aggregate
    assert "approval_history" in data
    assert "budget_ledger" in data


def test_get_workflow_detail_not_found(test_client, db_connection):
    """Test GET /api/operator/workflow/{id} returns 404 for missing workflow."""
    response = test_client.get("/api/operator/workflow/nonexistent")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_post_approve_validates_action(test_client, db_connection):
    """Test POST /api/operator/approve validates action field."""
    response = test_client.post(
        "/api/operator/approve",
        json={
            "workflow_id": "wf_test",
            "gate": "brief",
            "action": "reject",  # Not yet supported
        },
    )
    
    assert response.status_code == 400
    assert "approve" in response.json()["detail"].lower()


def test_kanban_card_includes_thumbnail(test_client, db_connection):
    """Test Kanban cards include thumbnail_url when available."""
    workflow_id = "wf_thumbnail"
    aggregate = {
        "workflow_id": workflow_id,
        "owner_user_id": "test-owner",
        "state": ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value,
        "product_name": "Test Product",
        "created_at": "2026-10-01T00:00:00Z",
        "latest_artifact": {
            "generated_keyframes": [
                {"image_url": "https://example.com/thumb.jpg"}
            ]
        },
    }
    
    db_connection.execute(
        "INSERT INTO workflow (workflow_id, aggregate_json, version) VALUES (?, ?, ?)",
        (workflow_id, json.dumps(aggregate), 1),
    )
    db_connection.commit()
    
    response = test_client.get("/api/operator/kanban")
    
    assert response.status_code == 200
    columns = response.json()["columns"]
    card = columns["awaiting_storyboard_approval"][0]
    
    assert card["thumbnail_url"] == "https://example.com/thumb.jpg"


def test_kanban_card_includes_estimated_cost(test_client, db_connection):
    """Test Kanban cards include estimated_cost when available."""
    workflow_id = "wf_cost"
    aggregate = {
        "workflow_id": workflow_id,
        "owner_user_id": "test-owner",
        "state": ProductVideoWorkflowState.RENDERING.value,
        "product_name": "Test Product",
        "created_at": "2026-10-01T00:00:00Z",
        "qc_authorization": {
            "workflow_max_cost_usd": 75.50
        },
    }
    
    db_connection.execute(
        "INSERT INTO workflow (workflow_id, aggregate_json, version) VALUES (?, ?, ?)",
        (workflow_id, json.dumps(aggregate), 1),
    )
    db_connection.commit()
    
    response = test_client.get("/api/operator/kanban")
    
    assert response.status_code == 200
    columns = response.json()["columns"]
    card = columns["in_production"][0]
    
    assert card["estimated_cost"] == 75.50


def test_get_product_workflows_returns_chain(test_client, db_connection):
    """Test GET /api/operator/product/{product_key}/workflows returns all created video variants."""
    pkey = "baseus_headphone_01"
    _create_test_workflow(db_connection, f"wf_{pkey}_vid_01", ProductVideoWorkflowState.COMPLETED.value)
    _create_test_workflow(db_connection, f"wf_{pkey}_vid_02", ProductVideoWorkflowState.RENDERING.value)
    _create_test_workflow(db_connection, "wf_other_prod", ProductVideoWorkflowState.COMPLETED.value)

    response = test_client.get(f"/api/operator/product/{pkey}/workflows")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["product_key"] == pkey
    assert len(data["workflows"]) == 2
    wf_ids = [w["workflow_id"] for w in data["workflows"]]
    assert f"wf_{pkey}_vid_01" in wf_ids
    assert f"wf_{pkey}_vid_02" in wf_ids


def test_re_render_scene_mismatched_id_fails_cleanly(test_client):
    """Test POST /api/operator/workflow/{id}/scene/re-render validates matching workflow_id."""
    response = test_client.post(
        "/api/operator/workflow/wf_123/scene/re-render",
        json={"workflow_id": "wf_mismatch", "scene_order": 3},
    )
    assert response.status_code == 400
    assert "Mismatched workflow_id" in response.json()["detail"]

