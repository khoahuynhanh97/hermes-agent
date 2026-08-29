"""Offline tests for Video Factory FastMCP server and Hermes wire tools compatibility."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pytest

from hermes.mcp.video_factory import server


def test_all_canonical_and_wire_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    tool_names = {t.name for t in tools}

    canonical_expected = {
        "video_project_create", "video_project_get", "resource_pack_save",
        "resource_pack_get", "resource_pack_lock", "resource_pack_unlock",
        "raw_idea_save", "creative_brief_save", "creative_brief_get",
        "creative_brief_approve", "scene_plan_save", "scene_plan_get",
        "scene_plan_approve", "storyboard_generate", "timeline_get",
        "export_submit", "video_factory_runtime_info",
    }
    assert canonical_expected.issubset(tool_names)

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


def test_create_brief_fails_closed_on_missing_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_brief.sqlite"))
    out = server.create_brief("fan_fa55", {"angle": "Silent Turbo"})
    assert out["ok"] is False
    assert out["code"] == "INVALID_INPUT"
    assert "missing required fields" in out["error"]


def test_create_brief_fails_closed_on_missing_project(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_brief_no_proj.sqlite"))
    valid_cfg = {
        "objective": "Convert hot commuters",
        "target_audience": "Subway riders",
        "core_message": "Silent portable cooling",
        "tone": "Direct",
        "pace": "Brisk",
        "cta": "Get 20% off today",
        "content_blocks": ["Hot commute dilemma", "Jisulife silent turbo", "Discount CTA"],
    }
    out = server.create_brief("fan_fa55", valid_cfg, owner_user_id="user_1", project_id="nonexistent_proj")
    assert out["ok"] is False
    assert out["code"] == "PROJECT_NOT_FOUND"


def test_create_brief_fails_closed_on_unlocked_resource_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_brief_unlocked.sqlite"))
    server.video_project_create("user_1", "proj_unlocked")
    valid_cfg = {
        "objective": "Convert hot commuters",
        "target_audience": "Subway riders",
        "core_message": "Silent portable cooling",
        "tone": "Direct",
        "pace": "Brisk",
        "cta": "Get 20% off today",
        "content_blocks": ["Hot commute dilemma", "Jisulife silent turbo", "Discount CTA"],
    }
    out = server.create_brief("fan_fa55", valid_cfg, owner_user_id="user_1", project_id="proj_unlocked")
    assert out["ok"] is False
    assert out["code"] == "RESOURCE_PACK_LOCKED_REQUIRED"


def test_create_brief_persists_canonical_input_with_locked_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_brief_ok.sqlite"))
    server.video_project_create("user_1", "proj_01")
    server.resource_pack_save("user_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    server.resource_pack_lock("user_1", "proj_01", {"description": "Black desk fan"})

    valid_cfg = {
        "objective": "Convert hot commuters",
        "target_audience": "Subway riders",
        "core_message": "Silent portable cooling",
        "tone": "Direct",
        "pace": "Brisk",
        "cta": "Get 20% off today",
        "content_blocks": ["Hot commute dilemma", "Jisulife silent turbo", "Discount CTA"],
    }
    out = server.create_brief("fan_fa55", valid_cfg, owner_user_id="user_1", project_id="proj_01")
    assert out["ok"] is True
    assert out["brief_id"] == "brief_fan_fa55"
    assert out["objective"] == "Convert hot commuters"
    assert out["project"]["creative_brief"]["objective"] == "Convert hot commuters"


def test_create_scene_plan_fails_closed_without_scenes(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_scene.sqlite"))
    out = server.create_scene_plan({"project_id": "proj_01"})
    assert out["ok"] is False
    assert out["code"] == "INVALID_INPUT"
    assert "missing required caller-supplied scenes" in out["error"]


def test_create_scene_plan_fails_closed_without_brief_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_scene_unapproved.sqlite"))
    server.video_project_create("owner_1", "proj_01")
    server.resource_pack_save("owner_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    server.resource_pack_lock("owner_1", "proj_01", {"description": "Black desk fan"})
    valid_cfg = {
        "objective": "Sales", "target_audience": "Riders", "core_message": "Cool",
        "tone": "Direct", "pace": "Fast", "cta": "Buy", "content_blocks": ["Intro"],
    }
    server.create_brief("fan_fa55", valid_cfg, owner_user_id="owner_1", project_id="proj_01")
    # Do NOT approve brief
    scenes = [{"scene_id": "s1", "order": 1, "title": "Hook", "objective": "Hook", "content": "Heat", "main_action": "Sweat", "duration_seconds": 3}]
    scene_out = server.create_scene_plan({"project_id": "proj_01", "scenes": scenes}, owner_user_id="owner_1", project_id="proj_01")
    assert scene_out["ok"] is False
    assert scene_out["code"] == "BRIEF_APPROVAL_REQUIRED"


def test_create_scene_plan_persists_canonical_scenes(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_scene_ok.sqlite"))
    server.video_project_create("owner_1", "proj_01")
    server.resource_pack_save("owner_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    server.resource_pack_lock("owner_1", "proj_01", {"description": "Black desk fan"})
    valid_cfg = {
        "objective": "Sales", "target_audience": "Riders", "core_message": "Cool",
        "tone": "Direct", "pace": "Fast", "cta": "Buy", "content_blocks": ["Intro"],
    }
    brief_out = server.create_brief("fan_fa55", valid_cfg, owner_user_id="owner_1", project_id="proj_01")
    server.creative_brief_approve("owner_1", "proj_01")
    scenes = [
        {"scene_id": "s1", "order": 1, "title": "Hook", "objective": "Hook", "content": "Heat", "main_action": "Sweat", "duration_seconds": 3},
        {"scene_id": "s2", "order": 2, "title": "Demo", "objective": "Demo", "content": "Fan", "main_action": "Cool", "duration_seconds": 5},
    ]
    brief_out["scenes"] = scenes
    scene_out = server.create_scene_plan(brief_out, owner_user_id="owner_1", project_id="proj_01")
    assert scene_out["ok"] is True
    assert len(scene_out["scenes"]) == 2
    assert scene_out["total_duration_seconds"] == 8


def test_create_storyboard_fails_closed_without_scene_plan_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_sb_unapproved.sqlite"))
    server.video_project_create("owner_1", "proj_01")
    server.resource_pack_save("owner_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    server.resource_pack_lock("owner_1", "proj_01", {"description": "Black desk fan"})
    valid_cfg = {
        "objective": "Sales", "target_audience": "Riders", "core_message": "Cool",
        "tone": "Direct", "pace": "Fast", "cta": "Buy", "content_blocks": ["Intro"],
    }
    server.create_brief("fan_fa55", valid_cfg, owner_user_id="owner_1", project_id="proj_01")
    server.creative_brief_approve("owner_1", "proj_01")
    scenes = [{"scene_id": "s1", "order": 1, "title": "Hook", "objective": "Hook", "content": "Heat", "main_action": "Sweat", "duration_seconds": 3}]
    server.create_scene_plan({"project_id": "proj_01", "scenes": scenes}, owner_user_id="owner_1", project_id="proj_01")
    # Do NOT approve scene plan
    sb_out = server.create_storyboard({"project_id": "proj_01"}, owner_user_id="owner_1", project_id="proj_01")
    assert sb_out["ok"] is False
    assert sb_out["code"] == "SCENE_PLAN_APPROVAL_REQUIRED"


def test_create_storyboard_generates_from_approved_scene_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_sb_ok.sqlite"))
    server.video_project_create("owner_1", "proj_01")
    server.resource_pack_save("owner_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    server.resource_pack_lock("owner_1", "proj_01", {"description": "Black desk fan"})
    valid_cfg = {
        "objective": "Sales", "target_audience": "Riders", "core_message": "Cool",
        "tone": "Direct", "pace": "Fast", "cta": "Buy", "content_blocks": ["Intro"],
    }
    server.create_brief("fan_fa55", valid_cfg, owner_user_id="owner_1", project_id="proj_01")
    server.creative_brief_approve("owner_1", "proj_01")
    scenes = [{"scene_id": "s1", "order": 1, "title": "Hook", "objective": "Hook", "content": "Heat", "main_action": "Sweat", "duration_seconds": 3}]
    server.create_scene_plan({"project_id": "proj_01", "scenes": scenes}, owner_user_id="owner_1", project_id="proj_01")
    server.scene_plan_approve("owner_1", "proj_01")

    sb_out = server.create_storyboard({"project_id": "proj_01"}, owner_user_id="owner_1", project_id="proj_01")
    assert sb_out["ok"] is True
    assert len(sb_out["frames"]) == 1


def test_render_and_export_fail_closed_truthfully(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "factory.sqlite"))
    monkeypatch.delenv("HERMES_VIDEO_FACTORY_PROVIDER", raising=False)
    server.video_project_create("user_1", "proj_1")

    render_out = server.render(owner_user_id="user_1", project_id="proj_1")
    assert render_out["ok"] is False
    assert render_out["status"] == "failed"
    assert render_out["code"] == "STORYBOARD_REQUIRED"

    export_out = server.export({})
    assert export_out["ok"] is False
    assert export_out["status"] == "failed"
    assert export_out["code"] == "MISSING_RENDER_OUTPUT"


def test_get_job_status_fails_closed_when_unconfigured_or_missing_id():
    out_empty = server.get_job_status("")
    assert out_empty["ok"] is False
    assert out_empty["code"] == "MISSING_JOB_ID"

    out_unconf = server.get_job_status("projects/p/locations/l/operations/op-1")
    assert out_unconf["ok"] is False
    assert out_unconf["status"] == "failed"
    assert out_unconf["code"] == "VF_PROVIDER_UNAVAILABLE"


def test_render_with_active_job_id_resumes_without_submitting():
    """Providing active_job_id must immediately return pending for that job ID without provider submit."""
    from unittest.mock import MagicMock

    mock_prov = MagicMock()
    out = server.render(
        render_params={"active_job_id": "projects/test-p/locations/us-central1/operations/op-active-123"},
        provider=mock_prov,
    )
    assert out["ok"] is True
    assert out["status"] == "pending"
    assert out["job_id"] == "projects/test-p/locations/us-central1/operations/op-active-123"
    mock_prov.submit.assert_not_called()


def test_render_submits_approved_storyboard_to_provider(tmp_path, monkeypatch):
    """Render submits approved project storyboard to provider and returns operation ID as job_id."""
    from unittest.mock import MagicMock
    from hermes.ports.video_generation import VideoGenerationResult

    db_path = tmp_path / "test_render.sqlite"
    ws_path = tmp_path / "test_render_ws"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_path))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws_path))

    # Setup project + locked pack + approved brief + approved scene plan + storyboard + approved storyboard
    server.video_project_create("user_r", "proj_r1")
    server.resource_pack_save("user_r", "proj_r1", {
        "id": "rp_r",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    server.resource_pack_lock("user_r", "proj_r1", {"description": "Black desk fan"})
    server.creative_brief_save("user_r", "proj_r1", {
        "objective": "Sales", "target_audience": "Office workers",
        "core_message": "Quiet air", "tone": "Calm", "pace": "Medium",
        "cta": "Buy now", "content_blocks": ["Intro"],
    })
    server.creative_brief_approve("user_r", "proj_r1")
    server.scene_plan_save("user_r", "proj_r1", {"scenes": [{
        "scene_id": "s1", "order": 1, "title": "Desk setup", "objective": "Show context",
        "content": "Hot office desk", "main_action": "Power on fan", "duration_seconds": 4,
    }]})
    server.scene_plan_approve("user_r", "proj_r1")
    server.storyboard_generate("user_r", "proj_r1")

    # Approve storyboard in repository
    srv = server._service()
    srv.approve_storyboard("user_r", "proj_r1")

    # Mock provider submit
    mock_prov = MagicMock()
    mock_prov.submit.return_value = VideoGenerationResult(
        request_id="req-1",
        status="submitted",
        provider_operation_id="projects/test-proj/locations/us-central1/operations/op-sub-777",
    )

    out = server.render(
        owner_user_id="user_r",
        project_id="proj_r1",
        render_params={"duration_seconds": 4, "aspect_ratio": "9:16"},
        provider=mock_prov,
    )
    assert out["ok"] is True
    assert out["status"] == "pending"
    assert out["job_id"] == "projects/test-proj/locations/us-central1/operations/op-sub-777"
    assert out["render_id"] == "render_op-sub-777"
    mock_prov.submit.assert_called_once()


def test_get_job_status_running_and_completed_with_real_mp4(tmp_path):
    """get_job_status polls provider and returns truthful running/completed status with MP4 evidence."""
    from unittest.mock import MagicMock
    from hermes.ports.video_generation import VideoGenerationResult

    mock_prov = MagicMock()

    # 1. Running state
    mock_prov.get_status.return_value = VideoGenerationResult(
        request_id="op-1",
        status="running",
        provider_operation_id="op-1",
    )
    res_running = server.get_job_status("op-1", provider=mock_prov)
    assert res_running["ok"] is True
    assert res_running["status"] == "running"
    assert res_running["job_id"] == "op-1"

    # 2. Completed state with real MP4
    mp4_file = tmp_path / "video_output.mp4"
    mp4_file.write_bytes(b"\x00\x00\x00\x18ftypmp42realdata")
    mock_prov.get_status.return_value = VideoGenerationResult(
        request_id="op-1",
        status="completed",
        video_path=str(mp4_file),
        provider_operation_id="projects/p/locations/l/operations/op-999",
    )
    res_completed = server.get_job_status("projects/p/locations/l/operations/op-999", provider=mock_prov)
    assert res_completed["ok"] is True
    assert res_completed["status"] == "completed"
    assert res_completed["video_url"] == f"file://{mp4_file.resolve()}"
    assert res_completed["render_id"] == "render_op-999"
    assert res_completed["file_size"] > 0


def test_deterministic_export_promotes_mp4_without_provider_call(tmp_path, monkeypatch):
    """export promotes completed MP4 to workspace exports directory deterministically and idempotently."""
    ws_path = tmp_path / "ws_export"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws_path))

    render_mp4 = tmp_path / "rendered_output.mp4"
    render_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42videoexportdata")

    rend_result = {
        "status": "completed",
        "video_url": f"file://{render_mp4.resolve()}",
        "render_id": "render_123",
        "project_id": "proj_export_1",
    }

    # First export
    out1 = server.export(render_result=rend_result, project_id="proj_export_1")
    assert out1["ok"] is True
    assert out1["status"] == "completed"
    assert "exports" in out1["final_video_url"]

    exported_file = Path(str(out1["final_video_url"]).removeprefix("file://"))
    assert exported_file.is_file()
    assert exported_file.read_bytes() == render_mp4.read_bytes()

    # Second export (idempotent replay)
    out2 = server.export(render_result=rend_result, project_id="proj_export_1")
    assert out2["ok"] is True
    assert out2["final_video_url"] == out1["final_video_url"]
    assert out2["file_size"] == out1["file_size"]


@pytest.mark.asyncio
async def test_wire_compatibility_tool_schemas_and_parameters():
    tools = await server.mcp.list_tools()
    by_name = {t.name: t.model_dump(by_alias=True) for t in tools}

    # Verify create_scene_plan schema exposes scenes and no required kwargs
    sp_schema = by_name["create_scene_plan"].get("inputSchema", {})
    assert "scenes" in sp_schema.get("properties", {})
    assert "kwargs" not in sp_schema.get("required", [])

    # Verify create_storyboard schema exposes frames and no required kwargs
    sb_schema = by_name["create_storyboard"].get("inputSchema", {})
    assert "frames" in sb_schema.get("properties", {})
    assert "kwargs" not in sb_schema.get("required", [])

    # Verify create_brief schema exposes product_id and brief_config
    br_schema = by_name["create_brief"].get("inputSchema", {})
    assert "product_id" in br_schema.get("properties", {})
    assert "brief_config" in br_schema.get("properties", {})
    assert "kwargs" not in br_schema.get("required", [])

    # Verify get_job_status requires only job_id
    job_schema = by_name["get_job_status"].get("inputSchema", {})
    assert "job_id" in job_schema.get("required", [])
    assert "kwargs" not in job_schema.get("required", [])
