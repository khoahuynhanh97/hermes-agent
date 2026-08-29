"""Focused offline contract tests for Video Factory MCP server and Hermes compatibility surface."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hermes.mcp.video_factory import server


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "contract_vf.sqlite"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_file))
    return db_file


def test_exact_tool_count_is_23():
    assert len(server.ALL_VIDEO_FACTORY_TOOLS) == 23
    assert len(server.CANONICAL_PUBLIC_TOOLS) == 17
    assert len(server.HERMES_WIRE_COMPATIBILITY_TOOLS) == 6
    assert set(tool.__name__ for tool in server.ALL_VIDEO_FACTORY_TOOLS) == {
        "video_project_create",
        "video_project_get",
        "resource_pack_save",
        "resource_pack_get",
        "resource_pack_lock",
        "resource_pack_unlock",
        "raw_idea_save",
        "creative_brief_save",
        "creative_brief_get",
        "creative_brief_approve",
        "scene_plan_save",
        "scene_plan_get",
        "scene_plan_approve",
        "storyboard_generate",
        "timeline_get",
        "export_submit",
        "video_factory_runtime_info",
        "create_brief",
        "create_scene_plan",
        "create_storyboard",
        "render",
        "export",
        "get_job_status",
    }


def test_create_brief_normalizes_legacy_inputs():
    result = server.create_brief("fan_fa55", brief_config={"angle": "Silent Turbo", "script": "Stay cool"})
    assert result["ok"] is True
    assert result["brief_id"] == "brief_fan_fa55"
    assert result["project_id"] == "proj_fan_fa55"
    assert result["objective"] == "Silent Turbo"
    assert result["core_message"] == "Stay cool"


def test_create_scene_plan_returns_three_steps():
    brief = server.create_brief("fan_fa55", brief_config={"angle": "Silent Turbo", "script": "Stay cool"})
    result = server.create_scene_plan(brief)
    assert result["ok"] is True
    assert len(result["scenes"]) == 3
    assert result["scenes"][0]["duration_seconds"] > 0


def test_create_storyboard_maps_scenes_to_frames():
    brief = server.create_brief("fan_fa55", brief_config={"angle": "Silent Turbo", "script": "Stay cool"})
    scene_plan = server.create_scene_plan(brief)
    result = server.create_storyboard(scene_plan)
    assert result["ok"] is True
    assert len(result["frames"]) == 3
    assert result["frames"][0]["scene_id"] == scene_plan["scenes"][0]["scene_id"]


def test_render_fails_closed_without_provider_or_mock():
    result = server.render({})
    assert result["status"] == "failed"
    assert result["code"] == "VF_PROVIDER_UNAVAILABLE"


def test_export_fails_closed_without_provider_or_mock():
    result = server.export({})
    assert result["status"] == "failed"
    assert result["code"] == "VF_EXPORT_UNAVAILABLE"


def test_get_job_status_is_fail_closed_for_unknown_job():
    result = server.get_job_status("job_unknown_123")
    assert result["status"] == "failed"
    assert result["code"] == "VF_PROVIDER_UNREACHABLE"


def test_render_and_export_honor_active_job_id():
    pending_render = server.render({}, render_params={"active_job_id": "render_existing"})
    assert pending_render["status"] == "pending"
    assert pending_render["job_id"] == "render_existing"

    pending_export = server.export(pending_render, export_params={"active_job_id": "export_existing"})
    assert pending_export["status"] == "pending"
    assert pending_export["job_id"] == "export_existing"


def test_runtime_info_exposes_hermes_home_paths():
    info = server.video_factory_runtime_info()
    assert info["canonical_tool_count"] == 17
    db_path = Path(info["database_path"])
    workspace_path = Path(info["workspace_path"])
    assert str(db_path) == str(server._db_path())
    assert str(workspace_path) == str(server._workspace_path())


def test_sqlite_persistence_survives_restart(tmp_db):
    first = server.video_project_create("owner_1", "proj_restart")
    assert first["ok"] is True
    assert first["project"]["status"] == "draft"

    pack_payload = {
        "id": "rp_restart",
        "product_references": [{"asset_id": "a1", "uri": "asset://product.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Restart durable fan",
    }
    server.resource_pack_save("owner_1", "proj_restart", pack_payload)
    server.resource_pack_lock("owner_1", "proj_restart", {"description": "Restart durable fan"})
    server.creative_brief_save("owner_1", "proj_restart", {
        "objective": "Sales",
        "target_audience": "Remote workers",
        "core_message": "Silent cooling",
        "tone": "Calm",
        "pace": "Medium",
        "cta": "Buy now",
        "content_blocks": ["Hook", "Demo", "CTA"],
    })
    server.creative_brief_approve("owner_1", "proj_restart")
    server.scene_plan_save("owner_1", "proj_restart", {"scenes": [{
        "scene_id": "s1", "order": 1, "title": "Hook", "objective": "Capture attention",
        "content": "Hot desk", "main_action": "Turn fan on", "duration_seconds": 3,
    }]})
    server.scene_plan_approve("owner_1", "proj_restart")
    server.storyboard_generate("owner_1", "proj_restart")

    repo = server.SQLiteVideoFactoryRepository(server._db_path())
    reloaded = repo.get_owned("proj_restart", "owner_1")
    assert reloaded is not None
    assert reloaded.status.value == "storyboard_ready"
    assert reloaded.resource_pack.locked_at is not None
    assert reloaded.creative_brief.objective == "Sales"
    assert len(reloaded.scene_plan.scenes) == 1
    assert len(reloaded.storyboard.frames) == 1


def test_owner_isolation_prevents_cross_user_access():
    server.video_project_create("owner_a", "proj_private")
    with pytest.raises(ValueError, match="PROJECT_NOT_FOUND"):
        server.video_project_get("owner_b", "proj_private")


def test_timeline_and_export_paths_remain_fail_closed_without_generated_scenes():
    server.video_project_create("owner_1", "proj_empty")
    with pytest.raises(ValueError, match="TIMELINE_NOT_FOUND"):
        server.timeline_get("owner_1", "proj_empty")

    with pytest.raises(ValueError, match="TIMELINE_NOT_FOUND"):
        server.export_submit("owner_1", "proj_empty")


def test_creative_brief_rejects_unsupported_status_and_missing_fields():
    with pytest.raises(ValueError, match="missing required fields"):
        server.creative_brief_save("owner_1", "proj_1", {"objective": "Sales"})

    with pytest.raises(ValueError, match="unsupported fields"):
        server.creative_brief_save("owner_1", "proj_1", {
            "objective": "Sales",
            "target_audience": "Remote workers",
            "core_message": "Silent cooling",
            "tone": "Calm",
            "pace": "Medium",
            "cta": "Buy now",
            "content_blocks": ["Hook"],
            "unsupported_field": "noop",
        })


def test_workspace_path_is_profile_scoped(monkeypatch, tmp_path):
    db_file = tmp_path / "profile_scope.sqlite"
    workspace_file = tmp_path / "workspaces" / "video-factory"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_file))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace_file))

    info = server.video_factory_runtime_info()
    assert Path(info["workspace_path"]) == workspace_file.resolve()
    assert Path(info["database_path"]) == db_file.resolve()
