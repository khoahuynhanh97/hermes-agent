import pytest

from mcp_servers.video_factory import server


def test_mcp_f1_workflow_and_owner_isolation(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "product.png").write_bytes(b"image")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "factory.sqlite"))

    project = server.video_project_create("owner-a", "p-1")["project"]
    server.resource_pack_save("owner-a", "p-1", {
        "id": "rp", "product_references": [{"asset_id": "a", "uri": "product.png"}],
        "primary_product_asset_id": "a", "product_identity_description": "lamp",
    })
    server.resource_pack_lock("owner-a", "p-1", {"description": "black lamp"})
    server.raw_idea_save("owner-a", "p-1", {"text": "review lamp"})
    server.creative_brief_save("owner-a", "p-1", {
        "objective": "demo", "target_audience": "buyers", "core_message": "easy",
        "tone": "direct", "pace": "fast", "cta": "buy", "content_blocks": ["hook", "demo"],
    })
    server.creative_brief_approve("owner-a", "p-1")
    server.scene_plan_save("owner-a", "p-1", {"scenes": [{
        "scene_id": "s1", "order": 1, "title": "Hook", "objective": "hook",
        "content": "show", "main_action": "place", "duration_seconds": 3,
    }]})
    result = server.scene_plan_approve("owner-a", "p-1")["project"]
    assert result["status"] == "ready_for_storyboard"
    assert server.video_project_get("owner-a", "p-1")["project"]["scene_plan"]["scenes"][0]["scene_id"] == "s1"
    with pytest.raises(ValueError, match="PROJECT_NOT_FOUND"):
        server.video_project_get("owner-b", "p-1")
