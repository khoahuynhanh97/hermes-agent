"""Verify the operator dashboard route serves the HTML entrypoint."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_personal.storage.sqlite import connect
from hermes_personal.application.app import create_application


@pytest.fixture
def client() -> TestClient:
    with tempfile.TemporaryDirectory() as tmpdir:
        connection = connect(Path(tmpdir) / "dashboard.db")
        app = create_application(enable_security_middleware=False, kanban_connection=connection)
        yield TestClient(app)
        connection.close()


def test_dashboard_route_serves_html(client: TestClient) -> None:
    """GET /dashboard returns 200 with the operator dashboard shell."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.text
    assert "Hermes Operator" in body
    assert "/operator/assets/dashboard.js" in body


def test_operator_alias_route_serves_html(client: TestClient) -> None:
    """GET /operator is an alias for the dashboard entrypoint."""
    response = client.get("/operator")
    assert response.status_code == 200
    assert "Hermes Operator" in response.text


def test_dashboard_static_asset_served(client: TestClient) -> None:
    """The dashboard JS bundle is reachable from the static mount."""
    response = client.get("/operator/assets/dashboard.js")
    assert response.status_code == 200
    assert "EventSource" in response.text


def test_kanban_endpoint_available_on_app(client: TestClient) -> None:
    """The operator router is mounted on the canonical application."""
    response = client.get("/api/operator/kanban")
    assert response.status_code == 200
    assert "columns" in response.json()