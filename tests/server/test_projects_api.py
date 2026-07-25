import pytest
import tempfile
from hermes.db import Database
from hermes.adapters.sqlite.project_repository import SQLiteProjectRepository
from fastapi.testclient import TestClient
from server.app import app
from server.dependencies import get_project_repository

tmp_db = tempfile.mktemp(suffix=".db")
database = Database(tmp_db)
database.initialize()
repo = SQLiteProjectRepository(tmp_db)

app.dependency_overrides[get_project_repository] = lambda: repo

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_project_returns_a_project_resource():
    response = client.post("/api/projects", json={"name": "Phone Stand"})
    assert response.status_code == 201
    assert response.json()["name"] == "Phone Stand"


def test_list_projects_returns_list():
    response = client.get("/api/projects")
    assert response.status_code == 200