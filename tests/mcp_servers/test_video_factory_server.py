"""Offline tests for Video Factory FastMCP server and Hermes wire tools compatibility."""
from __future__ import annotations

import asyncio
import os
import pytest

from hermes.mcp.video_factory import server


def test_all_canonical_and_wire_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    tool_names = {t.name for t in tools}

    # 17 Canonical tools
    canonical_expected = {
        "video_project_create", "video_project_get", "resource_pack_save",
        "resource_pack_get", "resource_pack_lock", "resource_pack_unlock",
        "raw_idea_save", "creative_brief_save", "creative_brief_get",
        "creative_brief_approve", "scene_plan_save", "scene_plan_get",
        "scene_plan_approve", "storyboard_generate", "timeline_get",
        "export_submit", "video_factory_runtime_info",
    }
    assert canonical_expected.issubset(tool_names)

    # 6 Hermes wire tools compatibility names
    wire_expected = {
        "create_brief", "create_scene_plan", "create_storyboard",
        "render", "export", "get_job_status",
    }
    assert wire_expected.issubset(tool_names)


def test_canonical_mcp_workflow_and_sqlite_persistence(tmp_path, monkeypatch):
    db_file = tmp_path / "factory_test.sqlite"
    ws_dir = tmp_path / "ws_test"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_file))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws_dir))

    # Create project
    res = server.video_project_create("user_x", "proj_x1")
    assert res["ok"] is True
    assert res["project"]["id"] == "proj_x1"

    # Save pack and lock
    server.resource_pack_save("user_x", "proj_x1", {
        "id": "rp_x",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    server.resource_pack_lock("user_x", "proj_x1", {"description": "Black desk fan"})

    # Brief
    server.creative_brief_save("user_x", "proj_x1", {
        "objective": "Sales", "target_audience": "Office workers",
        "core_message": "Quiet air", "tone": "Calm", "pace": "Medium",
        "cta": "Buy now", "content_blocks": ["Intro", "Outro"],
    })
    server.creative_brief_approve("user_x", "proj_x1")

    # Scene Plan
    server.scene_plan_save("user_x", "proj_x1", {"scenes": [{
        "scene_id": "s1", "order": 1, "title": "Desk setup", "objective": "Show context",
        "content": "Hot office desk", "main_action": "Power on fan", "duration_seconds": 4,
    }]})
    server.scene_plan_approve("user_x", "proj_x1")

    # Storyboard Generate
    sb_res = server.storyboard_generate("user_x", "proj_x1")
    assert sb_res["ok"] is True
    assert len(sb_res["project"]["storyboard"]["frames"]) == 1


def test_hermes_wire_tools_compatibility_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_test.sqlite"))

    # 1. create_brief
    brief_out = server.create_brief("fan_fa55", {"angle": "Silent Turbo Power", "script": "Stay cool at work"})
    assert brief_out["ok"] is True
    assert brief_out["brief_id"] is not None
    assert brief_out["product_id"] == "fan_fa55"
    assert brief_out["core_message"] == "Stay cool at work"

    # 2. create_scene_plan
    scene_out = server.create_scene_plan(brief_out)
    assert scene_out["ok"] is True
    assert len(scene_out["scenes"]) == 3
    assert scene_out["scenes"][0]["duration_seconds"] > 0

    # 3. create_storyboard
    sb_out = server.create_storyboard(scene_out)
    assert sb_out["ok"] is True
    assert len(sb_out["frames"]) == 3

    # 4. render (fail-closed offline when no provider configured)
    render_fail = server.render(sb_out)
    assert render_fail["status"] == "failed"
    assert "PROVIDER_NOT_CONFIGURED" in render_fail["error"]

    # 5. render (pre-computed / mock asset path)
    render_ok = server.render(sb_out, render_params={"mock_video_url": "asset://videos/output.mp4"})
    assert render_ok["status"] == "completed"
    assert render_ok["video_url"] == "asset://videos/output.mp4"

    # 6. export (fail-closed offline when no provider configured)
    export_fail = server.export(render_ok)
    assert export_fail["status"] == "failed"
    assert "PROVIDER_NOT_CONFIGURED" in export_fail["error"]

    # 7. export (pre-computed / mock asset path)
    export_ok = server.export(render_ok, export_params={"mock_export_url": "asset://exports/final.mp4"})
    assert export_ok["status"] == "completed"
    assert export_ok["export_url"] == "asset://exports/final.mp4"

    # 8. get_job_status
    status_done = server.get_job_status("job_completed_123")
    assert status_done["status"] == "completed"
    assert status_done["video_url"] == "asset://videos/job_completed_123.mp4"
