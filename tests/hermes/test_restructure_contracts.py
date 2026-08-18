import sys
from pathlib import Path
from fastapi.testclient import TestClient
from hermes.channels.api.app import app

def test_canonical_api_route_prefixes_registered():
    """Verify that Prompt Studio and Video Factory routes are registered under the correct prefixes in FastAPI."""
    client = TestClient(app)
    
    # Get OpenAPI schema to check registered routes
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json().get("paths", {})
    
    # Assert Prompt Studio paths exist under /api/prompt-studio/
    prompt_studio_paths = [p for p in paths if p.startswith("/api/prompt-studio/")]
    assert len(prompt_studio_paths) > 0, "No prompt studio routes found under /api/prompt-studio/"
    
    # Assert Video Factory paths exist under /api/vf/
    vf_paths = [p for p in paths if p.startswith("/api/vf/")]
    assert len(vf_paths) > 0, "No video factory routes found under /api/vf/"


def test_graphify_repomap_separation_static_assertion():
    """Ensure scripts/dev/graphify_graph_client.py has no dependency/import of RepoMap."""
    client_py = Path(__file__).resolve().parents[2] / "scripts" / "dev" / "graphify_graph_client.py"
    assert client_py.exists(), f"Graphify client script not found at {client_py}"
    
    content = client_py.read_text(encoding="utf-8")
    
    # Ensure no import of repo_map
    assert "repo_map" not in content.lower(), "graphify_graph_client.py must not import or reference repo_map"
    assert "hermes.application.core" not in content, "graphify_graph_client.py must not reference hermes.application.core"


def test_repository_root_layout_compliance():
    """Run the check_repository_structure script directly to assert repository compliance."""
    from scripts.dev.check_repository_structure import main
    import pytest
    
    try:
        main()
    except SystemExit as se:
        assert se.code == 0, "check_repository_structure exited with layout violations"


def test_runtime_layout_safe_resolver(monkeypatch, tmp_path):
    """Verify hermes.runtime_layout path getters, absolute root alignment, and traversal checks."""
    import os
    import pytest
    from hermes.runtime_layout import (
        get_data_root, get_jobs_dir, get_logs_dir, get_workspaces_dir,
        get_knowledge_dir, get_outputs_dir, get_caches_dir, get_artifacts_dir,
        get_work_journal_dir, get_project_workspace
    )
    
    # Mock data directory via environment variable
    fake_data_dir = tmp_path / "fake-data-dir"
    monkeypatch.setenv("HERMES_DATA_DIR", str(fake_data_dir))
    
    # Assert data root is correct
    root = get_data_root()
    assert root == fake_data_dir
    
    # Check directory resolutions
    assert get_jobs_dir() == fake_data_dir / "jobs"
    assert get_logs_dir() == fake_data_dir / "logs"
    assert get_workspaces_dir() == fake_data_dir / "workspaces"
    assert get_knowledge_dir() == fake_data_dir / "knowledge"
    assert get_outputs_dir() == fake_data_dir / "outputs"
    assert get_caches_dir() == fake_data_dir / "caches"
    assert get_artifacts_dir() == fake_data_dir / "artifacts"
    assert get_work_journal_dir() == fake_data_dir / "work-journal"
    
    # Check project workspace resolution
    project_dir = get_project_workspace("proj_baseus_wm02")
    assert project_dir == fake_data_dir / "workspaces" / "projects" / "proj_baseus_wm02"
    
    # Reject path traversal project ID
    with pytest.raises(ValueError, match="Invalid project_id characters"):
        get_project_workspace("../malicious_traversal")
        
    with pytest.raises(ValueError, match="Invalid project_id characters"):
        get_project_workspace("proj/sub")
        
    with pytest.raises(ValueError, match="Invalid project_id"):
        get_project_workspace("")


def test_frontend_asset_url_no_absolute_paths():
    """Verify backend API schemas and models do not contain absolute Windows/Unix filepath signatures."""
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    
    schema_str = response.text
    # We must not expose absolute path patterns or native file schemes in OpenAPI response models
    assert "file://" not in schema_str
    assert "D:\\" not in schema_str
    assert "C:\\" not in schema_str

