import asyncio

import pytest

from mcp_servers.video_factory import server


def test_resource_pack_tool_publishes_canonical_nested_schema():
    tools = asyncio.run(server.mcp.list_tools())
    tool = next(item for item in tools if item.name == "resource_pack_save")
    pack_schema = tool.inputSchema["properties"]["resource_pack"]
    resolved = tool.inputSchema.get("$defs", {}).get("ResourcePackInput", pack_schema)

    assert set(resolved["required"]) >= {
        "product_references",
        "primary_product_asset_id",
        "product_identity_description",
    }
    assert "files" not in resolved["properties"]
    assert "images" not in resolved["properties"]
    assert "product_name" not in resolved["properties"]


def test_creative_brief_tool_publishes_canonical_nested_schema():
    tools = asyncio.run(server.mcp.list_tools())
    tool = next(item for item in tools if item.name == "creative_brief_save")
    brief_schema = tool.inputSchema["properties"]["creative_brief"]
    resolved = tool.inputSchema.get("$defs", {}).get("CreativeBriefInput", brief_schema)

    assert set(resolved["required"]) >= {
        "objective", "target_audience", "core_message", "tone", "pace", "cta", "content_blocks"
    }
    assert "audience" not in resolved["properties"]
    assert "summary" not in resolved["properties"]
    assert "product_name" not in resolved["properties"]
    assert "objective" in tool.description
    assert "target_audience" in tool.description


def test_creative_brief_rejects_missing_canonical_fields():
    with pytest.raises(ValueError, match="missing required fields"):
        server._brief({
            "objective": "demo",
            "target_audience": "buyers",
            "core_message": "easy",
            "content_blocks": ["hook", "demo"],
        })


@pytest.mark.parametrize("claim", [
    {"claim": "25-hour battery"},
    {"claim": "Bluetooth 5.3", "status": "confirmed"},
    "lightweight",
])
def test_creative_brief_rejects_claims_without_canonical_status(claim):
    with pytest.raises(ValueError, match="verified_selling_points"):
        server._brief({
            "objective": "demo",
            "target_audience": "buyers",
            "core_message": "easy",
            "tone": "direct",
            "pace": "fast",
            "cta": "buy",
            "content_blocks": ["hook", "demo"],
            "verified_selling_points": [claim],
        })


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


def test_video_factory_runtime_info_tool_registered_and_resolves_paths(tmp_path, monkeypatch):
    db_file = tmp_path / "custom_factory.sqlite"
    ws_dir = tmp_path / "custom_workspace"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_file))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws_dir))

    tools = asyncio.run(server.mcp.list_tools())
    assert any(tool.name == "video_factory_runtime_info" for tool in tools)

    info = server.video_factory_runtime_info()
    assert info["database_path"] == str(db_file.resolve())
    assert info["workspace_path"] == str(ws_dir.resolve())
    assert "python_executable" in info
    assert "module_file" in info
