import pytest

from hermes_personal.integrations.video_factory import server


def test_resume_cannot_skip_owner_project_validation(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_VIDEO_FACTORY_DB_PATH', str(tmp_path / 'vf.db'))
    result = server.render(project_id='missing', owner_user_id='other',
                           render_params={'active_job_id': 'foreign-job'})
    assert result['ok'] is False


def test_unbound_operator_receipt_rejected(monkeypatch):
    from types import SimpleNamespace
    request = SimpleNamespace(status=SimpleNamespace(value='approved'), payload={})
    monkeypatch.setattr(server, '_approval_service', lambda: SimpleNamespace(get_request=lambda _: request))
    assert not server._verify_operator_approval('owner', 'project', 'Storyboard', 'receipt')[0]


def test_brief_does_not_fabricate_locked_pack(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_VIDEO_FACTORY_DB_PATH', str(tmp_path / 'vf.db'))
    result = server.create_brief('product', {'resource_pack': {'summary': 'unverified'}},
                                 owner_user_id='owner', project_id='project')
    assert result['ok'] is False
    with pytest.raises(ValueError):
        server._service().get_project('owner', 'project')


@pytest.mark.parametrize("gate_func,gate_name,kwargs", [
    (server.resource_pack_lock, "AwaitingProductLock", {"product_identity": {"description": "test"}}),
    (server.creative_brief_approve, "AwaitingBriefApproval", {}),
    (server.scene_plan_approve, "AwaitingSceneApproval", {}),
    (server.storyboard_approve, "AwaitingStoryboardApproval", {}),
    (server.final_video_approve, "AwaitingFinalApproval", {}),
])
def test_all_five_hitl_gates_fail_closed_without_receipt(gate_func, gate_name, kwargs, tmp_path, monkeypatch):
    """Prove that all 5 HITL gates fail closed when called without an operator approval receipt."""
    monkeypatch.setenv('HERMES_VIDEO_FACTORY_DB_PATH', str(tmp_path / 'vf.db'))
    server.video_project_create("owner", "proj")
    res = gate_func("owner", "proj", **kwargs)
    assert res["ok"] is False
    assert res["code"] == "OPERATOR_APPROVAL_REQUIRED"
    assert "missing approval_request_id" in res["error"]


@pytest.mark.parametrize("gate_func,gate_name,kwargs", [
    (server.resource_pack_lock, "AwaitingProductLock", {"product_identity": {"description": "test"}}),
    (server.creative_brief_approve, "AwaitingBriefApproval", {}),
    (server.scene_plan_approve, "AwaitingSceneApproval", {}),
    (server.storyboard_approve, "AwaitingStoryboardApproval", {}),
    (server.final_video_approve, "AwaitingFinalApproval", {}),
])
def test_all_five_hitl_gates_fail_closed_with_unapproved_or_mismatched_receipt(gate_func, gate_name, kwargs, tmp_path, monkeypatch):
    """Prove that all 5 HITL gates fail closed when called with a pending or foreign receipt."""
    from hermes_personal.storage.sqlite import connect
    from hermes_personal.workflows.approvals import ApprovalService

    approval_db = tmp_path / "approvals.db"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "vf.db"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(approval_db))

    conn = connect(approval_db)
    svc = ApprovalService(conn)

    # 1. Pending request (not approved by operator)
    pending_id = svc.submit_request({
        "owner_user_id": "owner",
        "project_id": "proj",
        "workflow_id": "proj",
        "gate": gate_name,
        "workflow_version": 1,
    })
    res_pending = gate_func("owner", "proj", approval_request_id=pending_id, **kwargs)
    assert res_pending["ok"] is False
    assert res_pending["code"] == "OPERATOR_APPROVAL_REQUIRED"
    assert "APPROVAL_NOT_GRANTED" in res_pending["error"]

    # 2. Foreign owner receipt
    foreign_id = svc.submit_request({
        "owner_user_id": "attacker",
        "project_id": "proj",
        "workflow_id": "proj",
        "gate": gate_name,
        "workflow_version": 1,
    })
    svc.approve(foreign_id)
    res_foreign = gate_func("owner", "proj", approval_request_id=foreign_id, **kwargs)
    assert res_foreign["ok"] is False
    assert res_foreign["code"] == "OPERATOR_APPROVAL_REQUIRED"
    assert "OWNER_MISMATCH" in res_foreign["error"]

    # 3. Wrong gate receipt
    wrong_gate_id = svc.submit_request({
        "owner_user_id": "owner",
        "project_id": "proj",
        "workflow_id": "proj",
        "gate": "SomeOtherGate",
        "workflow_version": 1,
    })
    svc.approve(wrong_gate_id)
    res_wrong_gate = gate_func("owner", "proj", approval_request_id=wrong_gate_id, **kwargs)
    assert res_wrong_gate["ok"] is False
    assert res_wrong_gate["code"] == "OPERATOR_APPROVAL_REQUIRED"
    assert "GATE_MISMATCH" in res_wrong_gate["error"]
    conn.close()


def test_gates_fail_closed_on_artifact_mismatch(tmp_path, monkeypatch):
    """Prove that HITL gate fails closed when approval receipt specifies an artifact_id that differs."""
    from hermes_personal.storage.sqlite import connect
    from hermes_personal.workflows.approvals import ApprovalService

    approval_db = tmp_path / "approvals_art.db"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "vf_art.db"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(approval_db))

    conn = connect(approval_db)
    svc = ApprovalService(conn)

    server.video_project_create("owner", "proj_art")
    server.resource_pack_save("owner", "proj_art", {
        "id": "actual_pack_id",
        "product_references": [{"asset_id": "a1", "uri": "asset://img.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "desc",
    })

    # Lock resource pack with artifact requirement
    req_id = svc.submit_request({
        "owner_user_id": "owner",
        "project_id": "proj_art",
        "workflow_id": "proj_art",
        "gate": "AwaitingProductLock",
        "artifact_id": "expected_pack_id_99",
    })
    svc.approve(req_id)

    # Caller passes different artifact_id
    res = server.resource_pack_lock(
        "owner", "proj_art",
        product_identity={"description": "desc", "artifact_id": "different_pack_id_11"},
        approval_request_id=req_id,
    )
    assert res["ok"] is False
    assert res["code"] == "OPERATOR_APPROVAL_REQUIRED"
    assert "ARTIFACT_MISMATCH" in res["error"]
    conn.close()


def test_render_fails_closed_without_admission_context(tmp_path, monkeypatch):
    """Prove that direct MCP render fails closed (ADMISSION_REQUIRED) when storyboard is approved but no worker admission context is provided."""
    from hermes_personal.storage.sqlite import connect
    from hermes_personal.workflows.approvals import ApprovalService

    approval_db = tmp_path / "approvals_render.db"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "vf_render.db"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(approval_db))

    conn = connect(approval_db)
    svc = ApprovalService(conn)

    server.video_project_create("owner", "proj_rend")
    server.resource_pack_save("owner", "proj_rend", {
        "id": "rp_rend",
        "product_references": [{"asset_id": "a1", "uri": "asset://img.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "d",
    })
    
    # Lock pack
    req1 = svc.submit_request({"owner_user_id": "owner", "project_id": "proj_rend", "gate": "AwaitingProductLock"})
    svc.approve(req1)
    lock_res = server.resource_pack_lock("owner", "proj_rend", product_identity={"description": "d"}, approval_request_id=req1)
    assert lock_res["ok"] is True

    # Brief
    brief_data = {
        "objective": "Sales", "target_audience": "Audience",
        "core_message": "Message", "tone": "Calm", "pace": "Medium",
        "cta": "Buy now", "content_blocks": ["Intro", "Outro"],
    }
    b_res = server.create_brief("prod", brief_data, owner_user_id="owner", project_id="proj_rend")
    assert b_res["ok"] is True
    req2 = svc.submit_request({"owner_user_id": "owner", "project_id": "proj_rend", "gate": "AwaitingBriefApproval"})
    svc.approve(req2)
    server.creative_brief_approve("owner", "proj_rend", approval_request_id=req2)

    # Scene Plan
    scenes = [{
        "scene_id": "s1", "order": 1, "title": "Intro", "objective": "Show product",
        "content": "Demo", "main_action": "Action", "duration_seconds": 5,
    }]
    s_res = server.create_scene_plan(b_res, owner_user_id="owner", project_id="proj_rend", scenes=scenes)
    assert s_res["ok"] is True
    req3 = svc.submit_request({"owner_user_id": "owner", "project_id": "proj_rend", "gate": "AwaitingSceneApproval"})
    svc.approve(req3)
    server.scene_plan_approve("owner", "proj_rend", approval_request_id=req3)

    # Storyboard Generate & Approve
    sb_res = server.storyboard_generate("owner", "proj_rend")
    assert sb_res["ok"] is True
    req4 = svc.submit_request({"owner_user_id": "owner", "project_id": "proj_rend", "gate": "AwaitingStoryboardApproval"})
    svc.approve(req4)
    server.storyboard_approve("owner", "proj_rend", approval_request_id=req4)

    # Attempt direct render without worker admission_context
    render_out = server.render(project_id="proj_rend", owner_user_id="owner")
    assert render_out["ok"] is False
    assert render_out["code"] == "ADMISSION_REQUIRED"

    # Attempt direct render with invalid reservation_id
    render_invalid = server.render(
        project_id="proj_rend",
        owner_user_id="owner",
        admission_context={"reservation_id": "res_non_existent"}
    )
    assert render_invalid["ok"] is False
    assert render_invalid["code"] == "ADMISSION_REQUIRED"
    conn.close()


class DummyProvider:
    def __init__(self):
        self.submit_count = 0

    def submit(self, req):
        self.submit_count += 1
        from types import SimpleNamespace
        return SimpleNamespace(status="submitted", provider_operation_id="op_123", error_message=None, error_code=None)

    def get_status(self, job_id):
        from types import SimpleNamespace
        return SimpleNamespace(status="running", video_path=None, error_message=None, error_code=None)


def test_provider_override_cannot_bypass_admission(tmp_path, monkeypatch):
    """Prove that provider injection does not bypass budget admission validation."""
    from hermes_personal.storage.sqlite import connect
    from hermes_personal.workflows.approvals import ApprovalService

    approval_db = tmp_path / "approvals_prov.db"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "vf_prov.db"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(approval_db))

    conn = connect(approval_db)
    svc = ApprovalService(conn)

    server.video_project_create("owner", "proj_override")
    server.resource_pack_save("owner", "proj_override", {
        "id": "rp_prov",
        "product_references": [{"asset_id": "a1", "uri": "asset://img.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "d",
    })
    req1 = svc.submit_request({"owner_user_id": "owner", "project_id": "proj_override", "gate": "AwaitingProductLock"})
    svc.approve(req1)
    server.resource_pack_lock("owner", "proj_override", product_identity={"description": "d"}, approval_request_id=req1)

    brief_data = {
        "objective": "Sales", "target_audience": "Audience",
        "core_message": "Message", "tone": "Calm", "pace": "Medium",
        "cta": "Buy now", "content_blocks": ["Intro", "Outro"],
    }
    b_res = server.create_brief("prod", brief_data, owner_user_id="owner", project_id="proj_override")
    req2 = svc.submit_request({"owner_user_id": "owner", "project_id": "proj_override", "gate": "AwaitingBriefApproval"})
    svc.approve(req2)
    server.creative_brief_approve("owner", "proj_override", approval_request_id=req2)

    scenes = [{
        "scene_id": "s1", "order": 1, "title": "Intro", "objective": "Show product",
        "content": "Demo", "main_action": "Action", "duration_seconds": 5,
    }]
    server.create_scene_plan(b_res, owner_user_id="owner", project_id="proj_override", scenes=scenes)
    req3 = svc.submit_request({"owner_user_id": "owner", "project_id": "proj_override", "gate": "AwaitingSceneApproval"})
    svc.approve(req3)
    server.scene_plan_approve("owner", "proj_override", approval_request_id=req3)

    server.storyboard_generate("owner", "proj_override")
    req4 = svc.submit_request({"owner_user_id": "owner", "project_id": "proj_override", "gate": "AwaitingStoryboardApproval"})
    svc.approve(req4)
    server.storyboard_approve("owner", "proj_override", approval_request_id=req4)

    provider = DummyProvider()
    res = server.render(
        project_id="proj_override",
        owner_user_id="owner",
        provider=provider,
    )
    assert res["ok"] is False
    assert res["code"] == "ADMISSION_REQUIRED"
    assert provider.submit_count == 0
    conn.close()


def test_export_fails_without_valid_project_and_final_approval(tmp_path, monkeypatch):
    """Prove export requires explicit project_id, project existence, and Final approval."""
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "vf_exp.db"))
    sample_mp4 = tmp_path / "sample.mp4"
    sample_mp4.write_bytes(b"fake mp4 content")
    lineage = {
        "video_url": f"file://{sample_mp4}", "owner_user_id": "owner",
        "workflow_id": "wf_export_guard", "artifact_id": "art_export_guard",
        "artifact_version": 1, "sha256": "a" * 64,
    }

    # 1. Missing project_id / proj_default
    res1 = server.export(
        render_result={"video_url": f"file://{sample_mp4}"},
        project_id="",
        owner_user_id="owner",
    )
    assert res1["ok"] is False
    assert res1["code"] == "RENDER_LINEAGE_REQUIRED"

    res2 = server.export(
        render_result={**lineage, "project_id": "proj_default"},
        project_id="proj_default",
        owner_user_id="owner",
    )
    assert res2["ok"] is False
    assert res2["code"] == "PROJECT_NOT_FOUND"

    # 2. Non-existent project
    res3 = server.export(
        render_result={**lineage, "project_id": "non_existent_proj"},
        project_id="non_existent_proj",
        owner_user_id="owner",
    )
    assert res3["ok"] is False
    assert res3["code"] == "PROJECT_NOT_FOUND"

    # 3. Project exists but final approval not granted
    server.video_project_create("owner", "proj_unappr")
    res4 = server.export(
        render_result={**lineage, "project_id": "proj_unappr"},
        project_id="proj_unappr",
        owner_user_id="owner",
    )
    assert res4["ok"] is False
    assert res4["code"] == "FINAL_APPROVAL_REQUIRED"


def test_canonical_gate_exact_match_and_version_zero(tmp_path, monkeypatch):
    """Prove canonical gate IDs are exact-match only (no aliases) and artifact version 0 is validated strictly."""
    from hermes_personal.storage.sqlite import connect
    from hermes_personal.workflows.approvals import ApprovalService

    approval_db = tmp_path / "approvals_canonical.db"
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "vf_canon.db"))
    monkeypatch.setenv("HERMES_APPROVAL_DB_PATH", str(approval_db))

    conn = connect(approval_db)
    svc = ApprovalService(conn)

    server.video_project_create("owner", "proj_v0")
    server.resource_pack_save("owner", "proj_v0", {
        "id": "rp_v0",
        "product_references": [{"asset_id": "a1", "uri": "asset://img.png"}],
        "primary_product_asset_id": "a1",
        "product_identity_description": "v0 desc",
    })

    # Request with legacy gate alias 'Product Lock' instead of canonical 'AwaitingProductLock'
    req_alias = svc.submit_request({
        "owner_user_id": "owner",
        "project_id": "proj_v0",
        "workflow_id": "proj_v0",
        "workflow_version": 1,
        "gate": "Product Lock",  # alias!
        "artifact_id": "rp_v0",
        "artifact_version": 0,
    })
    svc.approve(req_alias)

    # Must fail with GATE_MISMATCH because server requires canonical 'AwaitingProductLock'
    res_alias = server.resource_pack_lock(
        "owner", "proj_v0",
        product_identity={"description": "v0 desc"},
        approval_request_id=req_alias,
        workflow_id="proj_v0",
        workflow_version=1,
    )
    assert res_alias["ok"] is False
    assert "GATE_MISMATCH" in res_alias["error"]
    conn.close()
