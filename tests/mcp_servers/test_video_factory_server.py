"""Offline tests for Video Factory FastMCP server and Hermes wire tools compatibility."""
from __future__ import annotations

import asyncio
import os
import sys
from fractions import Fraction
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pytest
import av

try:
    from hermes_personal.integrations.video_factory import server
except ImportError:
    from hermes.mcp.video_factory import server
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.approvals import ApprovalService


GATE_MAP = {
    "Product Lock": "AwaitingProductLock",
    "AwaitingProductLock": "AwaitingProductLock",
    "Creative Brief": "AwaitingBriefApproval",
    "AwaitingBriefApproval": "AwaitingBriefApproval",
    "Scene Plan": "AwaitingSceneApproval",
    "AwaitingSceneApproval": "AwaitingSceneApproval",
    "Storyboard": "AwaitingStoryboardApproval",
    "AwaitingStoryboardApproval": "AwaitingStoryboardApproval",
    "Final Video": "AwaitingFinalApproval",
    "AwaitingFinalApproval": "AwaitingFinalApproval",
}


def test_resource_identity_parser_preserves_fidelity_fingerprint() -> None:
    identity = server._identity(
        {
            "description": "Ugreen Uno Robot 65W",
            "silhouette": "compact robotic cuboid with boot-shaped feet",
            "main_proportions": "body taller than wide",
            "product_count": "one charger",
            "control_placement": "three ports on top surface",
            "port_count": "three",
            "port_placement": "top surface only",
            "display_shape": "front square LED matrix",
        }
    )

    assert identity is not None
    assert identity.port_placement == "top surface only"
    assert identity.display_shape == "front square LED matrix"


def _write_valid_mp4(path: Path) -> Path:
    container = av.open(str(path), mode="w", format="mp4")
    stream = container.add_stream("libx264", rate=24)
    stream.width = 64
    stream.height = 96
    stream.pix_fmt = "yuv420p"
    for index in range(3):
        frame = av.VideoFrame(64, 96, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes([48 + index]) * plane.buffer_size)
        frame.pts = index
        frame.time_base = Fraction(1, 24)
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return path


def _create_approved_receipt(approval_db_path: Path, owner: str, project_id: str, gate: str) -> str:
    canonical_gate = GATE_MAP.get(gate, gate)
    conn = connect(approval_db_path)
    svc = ApprovalService(conn)
    req_id = svc.submit_request({
        "owner_user_id": owner,
        "project_id": project_id,
        "workflow_id": project_id,
        "gate": canonical_gate,
        "workflow_version": 1,
    })
    svc.approve(req_id)
    conn.close()
    return req_id


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


def test_product_lock_rejects_internal_pack_or_source_store_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "identity_guard.sqlite"))
    server.video_project_create("user_identity", "proj_identity")
    server.resource_pack_save("user_identity", "proj_identity", {
        "id": "rp_identity",
        "product_references": [{"asset_id": "a1", "uri": "asset://product.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "A real product",
    })

    for description in ("pack_snap_123", "Minh Gear product"):
        result = server.resource_pack_lock(
            "user_identity",
            "proj_identity",
            {"description": description},
        )
        assert result["ok"] is False
        assert result["code"] == "PRODUCT_IDENTITY_REQUIRED"


def test_canonical_mcp_workflow_and_sqlite_persistence(tmp_path, monkeypatch):
    db_file = tmp_path / "factory_test.sqlite"
    appr_file = tmp_path / "approvals.sqlite"
    ws_dir = tmp_path / "ws_test"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_file))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(appr_file))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws_dir))

    # Create project
    res = server.video_project_create("user_x", "proj_x1")
    assert res["ok"] is True
    assert res["project"]["id"] == "proj_x1"

    # Save pack and lock with operator receipt
    server.resource_pack_save("user_x", "proj_x1", {
        "id": "rp_x",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    lock_receipt = _create_approved_receipt(appr_file, "user_x", "proj_x1", "Product Lock")
    lock_res = server.resource_pack_lock("user_x", "proj_x1", {"description": "Black desk fan"}, approval_request_id=lock_receipt)
    assert lock_res["ok"] is True

    # Brief
    server.creative_brief_save("user_x", "proj_x1", {
        "objective": "Sales", "target_audience": "Office workers",
        "core_message": "Quiet air", "tone": "Calm", "pace": "Medium",
        "cta": "Buy now", "content_blocks": ["Intro", "Outro"],
    })
    brief_receipt = _create_approved_receipt(appr_file, "user_x", "proj_x1", "Creative Brief")
    brief_res = server.creative_brief_approve("user_x", "proj_x1", approval_request_id=brief_receipt)
    assert brief_res["ok"] is True

    # Scene Plan
    server.scene_plan_save("user_x", "proj_x1", {"scenes": [{
        "scene_id": "s1", "order": 1, "title": "Desk setup", "objective": "Show context",
        "content": "Hot office desk", "main_action": "Power on fan", "duration_seconds": 4,
    }]})
    scene_receipt = _create_approved_receipt(appr_file, "user_x", "proj_x1", "Scene Plan")
    scene_res = server.scene_plan_approve("user_x", "proj_x1", approval_request_id=scene_receipt)
    assert scene_res["ok"] is True

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
    appr_file = tmp_path / "approvals.sqlite"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_brief_ok.sqlite"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(appr_file))
    server.video_project_create("user_1", "proj_01")
    server.resource_pack_save("user_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    lock_receipt = _create_approved_receipt(appr_file, "user_1", "proj_01", "Product Lock")
    server.resource_pack_lock("user_1", "proj_01", {"description": "Black desk fan"}, approval_request_id=lock_receipt)

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
    appr_file = tmp_path / "approvals.sqlite"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_scene_unapproved.sqlite"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(appr_file))
    server.video_project_create("owner_1", "proj_01")
    server.resource_pack_save("owner_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    lock_receipt = _create_approved_receipt(appr_file, "owner_1", "proj_01", "Product Lock")
    server.resource_pack_lock("owner_1", "proj_01", {"description": "Black desk fan"}, approval_request_id=lock_receipt)
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
    appr_file = tmp_path / "approvals.sqlite"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_scene_ok.sqlite"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(appr_file))
    server.video_project_create("owner_1", "proj_01")
    server.resource_pack_save("owner_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    lock_receipt = _create_approved_receipt(appr_file, "owner_1", "proj_01", "Product Lock")
    server.resource_pack_lock("owner_1", "proj_01", {"description": "Black desk fan"}, approval_request_id=lock_receipt)
    valid_cfg = {
        "objective": "Sales", "target_audience": "Riders", "core_message": "Cool",
        "tone": "Direct", "pace": "Fast", "cta": "Buy", "content_blocks": ["Intro"],
    }
    brief_out = server.create_brief("fan_fa55", valid_cfg, owner_user_id="owner_1", project_id="proj_01")
    brief_receipt = _create_approved_receipt(appr_file, "owner_1", "proj_01", "Creative Brief")
    server.creative_brief_approve("owner_1", "proj_01", approval_request_id=brief_receipt)
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
    appr_file = tmp_path / "approvals.sqlite"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_sb_unapproved.sqlite"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(appr_file))
    server.video_project_create("owner_1", "proj_01")
    server.resource_pack_save("owner_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    lock_receipt = _create_approved_receipt(appr_file, "owner_1", "proj_01", "Product Lock")
    server.resource_pack_lock("owner_1", "proj_01", {"description": "Black desk fan"}, approval_request_id=lock_receipt)
    valid_cfg = {
        "objective": "Sales", "target_audience": "Riders", "core_message": "Cool",
        "tone": "Direct", "pace": "Fast", "cta": "Buy", "content_blocks": ["Intro"],
    }
    server.create_brief("fan_fa55", valid_cfg, owner_user_id="owner_1", project_id="proj_01")
    brief_receipt = _create_approved_receipt(appr_file, "owner_1", "proj_01", "Creative Brief")
    server.creative_brief_approve("owner_1", "proj_01", approval_request_id=brief_receipt)
    scenes = [{"scene_id": "s1", "order": 1, "title": "Hook", "objective": "Hook", "content": "Heat", "main_action": "Sweat", "duration_seconds": 3}]
    server.create_scene_plan({"project_id": "proj_01", "scenes": scenes}, owner_user_id="owner_1", project_id="proj_01")
    # Do NOT approve scene plan
    sb_out = server.create_storyboard({"project_id": "proj_01"}, owner_user_id="owner_1", project_id="proj_01")
    assert sb_out["ok"] is False
    assert sb_out["code"] == "SCENE_PLAN_APPROVAL_REQUIRED"


def test_create_storyboard_generates_from_approved_scene_plan(tmp_path, monkeypatch):
    appr_file = tmp_path / "approvals.sqlite"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "wire_sb_ok.sqlite"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(appr_file))
    server.video_project_create("owner_1", "proj_01")
    server.resource_pack_save("owner_1", "proj_01", {
        "id": "rp_01",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    lock_receipt = _create_approved_receipt(appr_file, "owner_1", "proj_01", "Product Lock")
    server.resource_pack_lock("owner_1", "proj_01", {"description": "Black desk fan"}, approval_request_id=lock_receipt)
    valid_cfg = {
        "objective": "Sales", "target_audience": "Riders", "core_message": "Cool",
        "tone": "Direct", "pace": "Fast", "cta": "Buy", "content_blocks": ["Intro"],
    }
    server.create_brief("fan_fa55", valid_cfg, owner_user_id="owner_1", project_id="proj_01")
    brief_receipt = _create_approved_receipt(appr_file, "owner_1", "proj_01", "Creative Brief")
    server.creative_brief_approve("owner_1", "proj_01", approval_request_id=brief_receipt)
    scenes = [{"scene_id": "s1", "order": 1, "title": "Hook", "objective": "Hook", "content": "Heat", "main_action": "Sweat", "duration_seconds": 3}]
    server.create_scene_plan({"project_id": "proj_01", "scenes": scenes}, owner_user_id="owner_1", project_id="proj_01")
    scene_receipt = _create_approved_receipt(appr_file, "owner_1", "proj_01", "Scene Plan")
    server.scene_plan_approve("owner_1", "proj_01", approval_request_id=scene_receipt)

    sb_out = server.create_storyboard({"project_id": "proj_01"}, owner_user_id="owner_1", project_id="proj_01")
    assert sb_out["ok"] is True
    assert len(sb_out["frames"]) == 1
    replay = server.create_storyboard({"project_id": "proj_01"}, owner_user_id="owner_1", project_id="proj_01")
    assert replay["ok"] is True
    assert replay["frames"] == sb_out["frames"]
    assert replay["project"]["storyboard_version"] == sb_out["project"]["storyboard_version"]


def test_render_and_export_fail_closed_truthfully(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "factory.sqlite"))
    server.video_project_create("user_1", "proj_1")

    render_out = server.render(owner_user_id="user_1", project_id="proj_1")
    assert render_out["ok"] is False
    assert render_out["status"] == "failed"
    assert render_out["code"] == "STORYBOARD_REQUIRED"

    export_out = server.export({
        "owner_user_id": "user_1", "project_id": "proj_1", "workflow_id": "workflow_1",
        "artifact_id": "artifact_1", "artifact_version": 1, "sha256": "a" * 64,
    })
    assert export_out["ok"] is False
    assert export_out["status"] == "failed"
    assert export_out["code"] == "MISSING_RENDER_OUTPUT"


def test_get_job_status_fails_closed_for_missing_id_or_ungoverned_poll():
    out_empty = server.get_job_status("")
    assert out_empty["ok"] is False
    assert out_empty["code"] == "MISSING_JOB_ID"

    out_ungoverned = server.get_job_status("projects/p/locations/l/operations/op-1")
    assert out_ungoverned["ok"] is False
    assert out_ungoverned["status"] == "failed"
    assert out_ungoverned["code"] == "VF_UNGOVERNED_POLL"


def test_render_with_active_job_id_resumes_without_submitting():
    """Providing active_job_id must immediately return pending for that job ID without provider submit."""
    from unittest.mock import MagicMock

    mock_prov = MagicMock()
    out = server.render(
        render_params={"active_job_id": "projects/test-p/locations/us-central1/operations/op-active-123"},
        provider=mock_prov,
    )
    assert out["ok"] is True, out
    assert out["status"] == "pending"
    assert out["job_id"] == "projects/test-p/locations/us-central1/operations/op-active-123"
    mock_prov.submit.assert_not_called()


def test_render_submits_approved_storyboard_to_provider(tmp_path, monkeypatch):
    """Render submits approved project storyboard to provider and returns operation ID as job_id."""
    from unittest.mock import MagicMock
    try:
        from hermes_personal.integrations.video_factory.ports import VideoGenerationResult
    except ImportError:
        from hermes.ports.video_generation import VideoGenerationResult

    db_path = tmp_path / "test_render.sqlite"
    appr_path = tmp_path / "test_render_appr.sqlite"
    ws_path = tmp_path / "test_render_ws"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_path))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(appr_path))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws_path))

    # Setup project + locked pack + approved brief + approved scene plan + storyboard + approved storyboard
    server.video_project_create("user_r", "proj_r1")
    server.resource_pack_save("user_r", "proj_r1", {
        "id": "rp_r",
        "product_references": [{"asset_id": "a1", "uri": "asset://fan.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "Desk fan",
    })
    lock_receipt = _create_approved_receipt(appr_path, "user_r", "proj_r1", "Product Lock")
    server.resource_pack_lock("user_r", "proj_r1", {"description": "Black desk fan"}, approval_request_id=lock_receipt)
    server.creative_brief_save("user_r", "proj_r1", {
        "objective": "Sales", "target_audience": "Office workers",
        "core_message": "Quiet air", "tone": "Calm", "pace": "Medium",
        "cta": "Buy now", "content_blocks": ["Intro"],
    })
    brief_receipt = _create_approved_receipt(appr_path, "user_r", "proj_r1", "Creative Brief")
    server.creative_brief_approve("user_r", "proj_r1", approval_request_id=brief_receipt)
    server.scene_plan_save("user_r", "proj_r1", {"scenes": [{
        "scene_id": "s1", "order": 1, "title": "Desk setup", "objective": "Show context",
        "content": "Hot office desk", "main_action": "Power on fan", "duration_seconds": 4,
    }]})
    scene_receipt = _create_approved_receipt(appr_path, "user_r", "proj_r1", "Scene Plan")
    server.scene_plan_approve("user_r", "proj_r1", approval_request_id=scene_receipt)
    server.storyboard_generate("user_r", "proj_r1")

    # Approve storyboard in repository
    srv = server._service()
    srv.approve_storyboard("user_r", "proj_r1")

    # Mock provider submit
    mock_prov = MagicMock()
    mock_prov.provider_kind = "vertex_ai"
    mock_prov.model = "offline-provider"
    mock_prov.submit.return_value = VideoGenerationResult(
        request_id="req-1",
        status="submitted",
        provider_operation_id="projects/test-proj/locations/us-central1/operations/op-sub-777",
    )

    from hermes_personal.workflows.budgets import init_default_engine, BudgetPolicy, reserve_budget
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_generation": 1000}))
    alloc = reserve_budget("video_generation", 100, owner_user_id="user_r", scope_id="proj_r1")

    out = server.render(
        owner_user_id="user_r",
        project_id="proj_r1",
        render_params={"duration_seconds": 4, "aspect_ratio": "9:16"},
        admission_context={"reservation_id": alloc.reservation_id},
        provider=mock_prov,
    )
    assert out["ok"] is True, out
    assert out["status"] == "pending"
    assert out["job_id"].startswith("batch_proj_r1")
    assert out["render_id"].startswith("batch_proj_r1")
    mock_prov.submit.assert_called_once()
    submitted_req = mock_prov.submit.call_args.args[0]
    assert "shop name" in submitted_req.prompt
    assert "source-store branding" in submitted_req.prompt
    assert "seller name" in submitted_req.provider_options["negativePrompt"]
    assert "Minh Gear" not in submitted_req.prompt
    assert "Minh Gear" not in submitted_req.provider_options["negativePrompt"]
    assert "watermark" in submitted_req.provider_options["negativePrompt"]


def test_get_job_status_rejects_ungoverned_single_scene_polling():
    """Single-scene polling cannot bypass the durable render-batch contract."""
    from unittest.mock import MagicMock

    mock_prov = MagicMock()
    result = server.get_job_status(
        "projects/p/locations/l/operations/op-999",
        provider=mock_prov,
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["code"] == "VF_UNGOVERNED_POLL"
    mock_prov.get_status.assert_not_called()


def test_deterministic_export_promotes_mp4_without_provider_call(tmp_path, monkeypatch):
    """export promotes completed MP4 to workspace exports directory deterministically and idempotently."""
    db_file = tmp_path / "factory_export.sqlite"
    ws_path = tmp_path / "ws_export"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_file))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws_path))

    from hermes_personal.integrations.video_factory.service import FinalApprovalStatus, VideoFactoryProject
    server.video_project_create("user_export", "proj_export_1")
    server.resource_pack_save("user_export", "proj_export_1", {
        "id": "rp_export",
        "product_references": [{"asset_id": "a1", "uri": "asset://keyboard.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "AULA F75 mechanical keyboard",
    })
    srv = server._service()
    proj = srv.get_project("user_export", "proj_export_1")
    srv.repository.save(VideoFactoryProject(
        **{**proj.__dict__, "final_approval": FinalApprovalStatus.APPROVED}
    ))

    source_path = ws_path / "projects" / "proj_export_1" / "renders" / "v1" / "composite" / "draft.mp4"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    render_mp4 = _write_valid_mp4(source_path)
    from hermes_personal.integrations.video_factory.domain import VideoFactoryArtifact
    from hermes_personal.integrations.video_factory.composer import VideoExpectation, probe_video, compute_file_sha256
    srv.repository.save_artifact(VideoFactoryArtifact(
        artifact_id="art_export", owner_user_id="user_export", workflow_id="wf_export",
        project_id="proj_export_1", kind="composite",
        relative_path=render_mp4.relative_to(ws_path).as_posix(),
        sha256=compute_file_sha256(render_mp4), size=render_mp4.stat().st_size,
        mime_type="video/mp4", version=1,
    ))
    from hermes_personal.product_video.qc.repository import QCReportRepository
    from hermes_personal.product_video.qc.models import QCReport, QCStage, QCVerdict
    import sqlite3
    qc_conn = sqlite3.connect(db_file)
    QCReportRepository(qc_conn).save_report(
        QCReport(
            report_id="qc-export-1",
            workflow_id="wf_export",
            stage=QCStage.VIDEO,
            artifact_id="art_export",
            artifact_version=1,
            artifact_digest=f"sha256:{compute_file_sha256(render_mp4)}",
            reference_digests=(),
            evaluator_name="evaluator",
            evaluator_version="1.0",
            rubric_version="1.0",
            created_at="2026-09-17T00:00:00Z",
            score=95,
            verdict=QCVerdict.PASS,
            findings=(),
            owner_user_id="user_export",
            project_id="proj_export_1",
        )
    )
    qc_conn.close()
    monkeypatch.setattr(
        server,
        "_EXPORT_VIDEO_EXPECTATION",
        VideoExpectation(
            width=64,
            height=96,
            duration_seconds=probe_video(render_mp4).duration_seconds,
            codec="h264",
            fps=24.0,
            min_frames=1,
            max_duration_delta=0.5,
        ),
    )

    rend_result = {
        "status": "completed",
        "video_url": f"file://{render_mp4.resolve()}",
        "render_id": "render_123",
        "project_id": "proj_export_1",
        "owner_user_id": "user_export",
        "workflow_id": "wf_export",
        "artifact_id": "art_export",
        "artifact_version": 1,
        "sha256": compute_file_sha256(render_mp4),
    }

    # First export
    out1 = server.export(render_result=rend_result, project_id="proj_export_1", owner_user_id="user_export")
    assert out1["ok"] is True, out1
    assert out1["status"] == "completed"
    assert "exports" in out1["final_video_url"]

    exported_file = Path(str(out1["final_video_url"]).removeprefix("file://"))
    assert exported_file.is_file()
    assert exported_file.read_bytes() == render_mp4.read_bytes()
    caption_text = Path(out1["caption_path"]).read_text(encoding="utf-8")
    assert "AULA F75 mechanical keyboard" in caption_text
    assert "pack_snap" not in caption_text
    assert "đặt hàng" not in caption_text.lower()
    assert "#review" not in caption_text

    # Second export (idempotent replay)
    out2 = server.export(render_result=rend_result, project_id="proj_export_1", owner_user_id="user_export")
    assert out2["ok"] is True
    assert out2["final_video_url"] == out1["final_video_url"]
    assert out2["file_size"] == out1["file_size"]



def test_export_fails_when_caption_identity_is_pack_id_or_generic(tmp_path, monkeypatch):
    db_file = tmp_path / "factory_bad_caption.sqlite"
    ws_path = tmp_path / "ws_bad_caption"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_file))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(ws_path))

    from hermes_personal.integrations.video_factory.service import FinalApprovalStatus, VideoFactoryProject
    server.video_project_create("user_export", "proj_bad_caption")
    server.resource_pack_save("user_export", "proj_bad_caption", {
        "id": "pack_snap_123",
        "product_references": [{"asset_id": "a1", "uri": "asset://bad.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "pack_snap_123",
    })
    srv = server._service()
    proj = srv.get_project("user_export", "proj_bad_caption")
    srv.repository.save(VideoFactoryProject(
        **{**proj.__dict__, "final_approval": FinalApprovalStatus.APPROVED}
    ))

    render_mp4 = tmp_path / "rendered_output.mp4"
    render_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42videoexportdata")

    out = server.export(
        render_result={
            "status": "completed",
            "video_url": f"file://{render_mp4.resolve()}",
            "render_id": "render_bad_caption",
            "project_id": "proj_bad_caption",
            "owner_user_id": "user_export",
            "workflow_id": "wf_bad_caption", "artifact_id": "art_bad_caption",
            "artifact_version": 1, "sha256": "a" * 64,
        },
        project_id="proj_bad_caption",
        owner_user_id="user_export",
    )

    assert out["ok"] is False
    assert out["code"] == "PRODUCT_IDENTITY_REQUIRED"


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
