import asyncio
import json

from hermes.security.ingress import build_gateway_principal, principal_scope
from hermes.tools import product_to_video_tool


def test_agent_visible_product_video_tool_requires_user_approval(monkeypatch):
    captured = {}

    class FakeOrchestrator:
        def __init__(self, db_path):
            captured["db_path"] = db_path

        def run_product_to_video_workflow(self, **kwargs):
            captured["kwargs"] = kwargs
            return {"status": "approval_required", "approval_stage": "creative_brief"}

    monkeypatch.setattr("hermes.application.workflow.WorkflowOrchestrator", FakeOrchestrator)
    principal = build_gateway_principal(
        actor_id="42",
        owner_user_id="42",
        platform="telegram",
        session_id="telegram:100",
    )

    with principal_scope(principal):
        raw = product_to_video_tool._handle_product_to_video(
            prompt="create video",
            owner_user_id="attacker-selected-owner",
        )

    result = json.loads(raw)
    assert result["status"] == "approval_required"
    assert captured["kwargs"]["owner_user_id"] == "42"
    assert captured["kwargs"]["approval_policy"] == "require_user"


def test_user_governed_workflow_routes_async_flag_to_approval_boundary(monkeypatch, tmp_path):
    from hermes.application.workflow import WorkflowOrchestrator

    orchestrator = WorkflowOrchestrator(tmp_path / "workflow.sqlite")
    monkeypatch.setattr(
        orchestrator,
        "dispatch_product_to_video_workflow",
        lambda **_: {"status": "approval_required", "approval_stage": "creative_brief"},
    )

    result = orchestrator.run_product_to_video_workflow(
        prompt="create video",
        async_dispatch=True,
        approval_policy="require_user",
    )

    assert result == {"status": "approval_required", "approval_stage": "creative_brief"}


def test_model_facing_video_factory_mcp_excludes_approval_mutations():
    from hermes.mcp.video_factory import server

    names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}

    assert "creative_brief_approve" not in names
    assert "scene_plan_approve" not in names
    assert "storyboard_approve" not in names
    assert "final_approve" not in names
