from pathlib import Path
import pytest
import sqlite3

from hermes.adapters.sqlite.project_repository import SQLiteProjectRepository
from hermes.db import Database


@pytest.fixture
def in_memory_db():
    db = Database(":memory:")
    db.initialize()
    return db


@pytest.fixture
def project_repository(in_memory_db):
    return SQLiteProjectRepository(in_memory_db.path)


def test_project_repository_persists_a_project_across_connections(tmp_path):
    db_path = tmp_path / "hermes.db"
    repo1 = SQLiteProjectRepository(db_path)
    created = repo1.create("Phone Stand", str(tmp_path / "phone_stand_root"))
    assert created.ok
    assert created.value is not None

    repo2 = SQLiteProjectRepository(db_path)
    loaded = repo2.get(created.value.id)
    assert loaded.ok
    assert loaded.value.name == "Phone Stand"
    assert loaded.value.filesystem_root == str(tmp_path / "phone_stand_root")


def test_project_repository_returns_not_found_for_non_existent_project(project_repository):
    result = project_repository.get("non-existent-id")
    assert not result.ok
    assert result.error_code == "not_found"


def test_project_repository_lists_active_projects(project_repository, tmp_path):
    repo_path = tmp_path / "test_repo.db"
    repo = SQLiteProjectRepository(repo_path)
    repo.create("Project A", str(tmp_path / "project_a"))
    repo.create("Project B", str(tmp_path / "project_b"))
    
    active_projects = repo.list_active()
    assert active_projects.ok
    assert len(active_projects.value) == 2
    assert {p.name for p in active_projects.value} == {"Project A", "Project B"}


def test_project_repository_archives_project(project_repository, tmp_path):
    repo_path = tmp_path / "test_repo_archive.db"
    repo = SQLiteProjectRepository(repo_path)
    created = repo.create("Project to Archive", str(tmp_path / "archive_root"))
    assert created.ok

    archive_result = repo.archive(created.value.id)
    assert archive_result.ok

    reloaded_project = repo.get(created.value.id)
    assert reloaded_project.ok
    assert not reloaded_project.value.is_active


def test_project_repository_cannot_create_duplicate_project_name(project_repository, tmp_path):
    project_repository.create("Duplicate Name", str(tmp_path / "dup1"))
    result = project_repository.create("Duplicate Name", str(tmp_path / "dup2"))
    assert not result.ok
    assert result.error_code == "conflict"


def test_project_repository_initializes_db_schema(tmp_path):
    db_path = tmp_path / "new_hermes.db"
    # Initializing the repository should create the schema
    repo = SQLiteProjectRepository(db_path)

    # Verify tables exist
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workflows'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_steps'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assets'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='artifacts'")
        assert cursor.fetchone() is not None
