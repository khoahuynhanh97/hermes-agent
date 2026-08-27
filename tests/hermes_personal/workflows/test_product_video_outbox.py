import json
import sqlite3
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from hermes_personal.application.app import create_application
from hermes_personal.application.events_api import EventsAPI
from hermes_personal.application.operator_handler import create_operator_command_handler

from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.approvals import ApprovalService
from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine, get_allocated_budget
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.envelope import build_envelope, parse_envelope
from hermes_personal.workflows.outbox_dispatcher import DispatchReport, OutboxDispatcher
from hermes_personal.workflows.outbox_repository import OutboxRepository
from hermes_personal.workflows.repository import WorkflowRepository
from hermes_personal.workflows.worker import run_worker
from hermes_personal.product_video.handlers import (
    ProductVideoWorkflowState,
    JobContext,
    JobSucceeded,
    ProductVideoJobHandlers,
    register_product_video_job_handlers,
    create_product_video_topic_handlers,
    start_product_video_workflow,
)


def _init_db(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workflow (
            workflow_id TEXT PRIMARY KEY,
            aggregate_json TEXT,
            version INTEGER
        );
        CREATE TABLE IF NOT EXISTS processed_command (
            workflow_id TEXT,
            command_id TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS workflow_event (
            event_id TEXT PRIMARY KEY,
            workflow_id TEXT,
            event_type TEXT,
            timestamp TEXT,
            payload_json TEXT
        );
        CREATE TABLE IF NOT EXISTS workflow_outbox (
            outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id TEXT NOT NULL,
            message TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            lease_token TEXT,
            lease_owner TEXT,
            lease_expires_at TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            last_error TEXT,
            next_attempt_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS approval_request (
            request_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS budget_reservation (
            reservation_id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            status TEXT NOT NULL,
            workflow_id TEXT,
            job_id TEXT,
            idempotency_key TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


@pytest.fixture
def env(tmp_path):
    db_file = tmp_path / "hermes.db"
    conn = sqlite3.connect(str(db_file))
    _init_db(conn)
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))
    yield conn
    conn.close()


def test_product_video_job_dispatch_is_enqueued_as_outbox(env):
    wf_id = "wf_happy_01"
    repo = WorkflowRepository(env)
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.CREATING_BRIEF.value}),
        events=[{"event_id": "e1", "command_id": "c1", "event_type": "JobDispatched", "timestamp": "2026-01-01T00:00:00Z", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_brief_1",
            payload={"job_name": "product_video.creative_brief", "workflow_id": wf_id, "args": ["prod_1"]},
        ),
        expected_version=0,
    )

    outbox_repo = OutboxRepository(env)
    pending = outbox_repo.list_unacknowledged()
    assert len(pending) == 1
    assert pending[0].workflow_id == wf_id
    envelope = parse_envelope(pending[0].message)
    assert envelope.topic == "job.dispatch"
    assert envelope.payload["job_name"] == "product_video.creative_brief"


def test_outbox_worker_delivers_product_video_job_through_handler(env):
    wf_id = "wf_happy_02"
    repo = WorkflowRepository(env)
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RESEARCHING.value}),
        events=[{"event_id": "e1", "command_id": "c1", "event_type": "JobDispatched", "timestamp": "2026-01-01T00:00:00Z", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_res_1",
            payload={"job_name": "product_video.research", "workflow_id": wf_id, "args": ["TikTok Wireless Earbuds ANC", ["bluetooth", "anc"]]},
        ),
        expected_version=0,
    )

    engine = WorkflowEngine(repo)
    handlers = register_product_video_job_handlers(dispatcher={}, workflow_engine=engine)

    def topic_handler(envelope):
        payload = envelope.payload
        job_name = payload["job_name"]
        target_wf = payload["workflow_id"]
        handler = handlers[job_name]
        ctx = JobContext(
            workflow_id=target_wf,
            job_id=f"{job_name}.auto",
            expected_version=engine.get_workflow_state(target_wf)[1],
            idempotency_key=envelope.idempotency_key,
        )
        result = handler(ctx, *payload.get("args", []))
        assert isinstance(result, JobSucceeded)

    outbox_repo = OutboxRepository(env)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers={"job.dispatch": topic_handler}, worker_id="worker-1")
    report = dispatcher.process_batch(now_iso="2026-01-01T00:00:00Z")

    assert report == DispatchReport(claimed=1, succeeded=1, failed=0, quarantined=0)
    assert outbox_repo.list_unacknowledged() == []
    assert get_allocated_budget("video_factory") == 0


def test_unconfigured_handler_fails_closed_and_preserves_outbox(env):
    wf_id = "wf_happy_03"
    repo = WorkflowRepository(env)
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.CREATING_BRIEF.value}),
        events=[{"event_id": "e1", "command_id": "c1", "event_type": "JobDispatched", "timestamp": "2026-01-01T00:00:00Z", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_brief_3",
            payload={"job_name": "product_video.creative_brief", "workflow_id": wf_id, "args": ["prod_1"]},
        ),
        expected_version=0,
    )

    outbox_repo = OutboxRepository(env)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers={}, worker_id="worker-1")
    report = dispatcher.process_batch(now_iso="2026-01-01T00:00:00Z")

    assert report.claimed == 1
    assert outbox_repo.list_unacknowledged()
    state, _ = WorkflowEngine(WorkflowRepository(env)).get_workflow_state(wf_id)
    assert state == ProductVideoWorkflowState.CREATING_BRIEF.value
    assert get_allocated_budget("video_factory") == 0


def test_product_video_happy_path_survives_restart_and_approval(env):
    wf_id = "wf_happy_04"
    pdp_url = "https://shop.tiktok.com/view/product/17294829104"
    repo = WorkflowRepository(env)
    engine = WorkflowEngine(env)
    approval_service = ApprovalService(env)
    budget_before = get_allocated_budget("video_factory")

    first_message = build_envelope(
        workflow_id=wf_id,
        topic="job.dispatch",
        idempotency_key="idemp_res_1",
        payload={"job_name": "product_video.research", "workflow_id": wf_id, "args": ["TikTok Wireless Earbuds ANC", ["bluetooth", "anc"], pdp_url]},
    )
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RESEARCHING.value}),
        events=[{"event_id": "e1", "command_id": "c1", "event_type": "JobDispatched", "timestamp": "2026-01-01T00:00:00Z", "payload": {}}],
        outbox_message=first_message,
        expected_version=0,
    )

    db_path = env.execute("PRAGMA database_list").fetchall()[0][2]
    env.close()

    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    repo2 = WorkflowRepository(conn2)
    engine2 = WorkflowEngine(repo2)
    handlers = register_product_video_job_handlers(dispatcher={}, workflow_engine=engine2)
    approval_service2 = ApprovalService(conn2)

    def topic_handler(envelope):
        payload = envelope.payload
        job_name = payload["job_name"]
        target_wf = payload["workflow_id"]
        handler = handlers[job_name]
        ctx = JobContext(
            workflow_id=target_wf,
            job_id=f"{job_name}.auto",
            expected_version=engine2.get_workflow_state(target_wf)[1],
            idempotency_key=envelope.idempotency_key,
        )
        result = handler(ctx, *payload.get("args", []))
        assert isinstance(result, JobSucceeded)

    outbox_repo = OutboxRepository(conn2)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers={"job.dispatch": topic_handler}, worker_id="worker-1")
    report = dispatcher.process_batch(now_iso="2026-01-01T00:00:00Z")
    assert report == DispatchReport(claimed=1, succeeded=1, failed=0, quarantined=0)
    assert outbox_repo.list_unacknowledged() == []
    assert get_allocated_budget("video_factory") == budget_before

    req_id = approval_service2.submit_request({
        "workflow_id": wf_id,
        "gate": "AwaitingProductLock",
        "channel": "web",
        "workflow_version": 1,
        "pdp_url": pdp_url,
    })
    approval_service2.approve(req_id)
    assert approval_service2.get_request(req_id).status.value == "approved"
    assert get_allocated_budget("video_factory") == budget_before
    conn2.close()


def test_production_entrypoint_and_create_product_video_topic_handlers(tmp_path):
    """Test full production producer (start_product_video_workflow) -> SQLite reopen ->
    create_product_video_topic_handlers -> process outbox -> artifact persisted -> HITL gate."""
    db_file = tmp_path / "prod_pv.db"
    conn = connect(db_file)

    repo = WorkflowRepository(conn)
    wf_id = "wf_prod_01"
    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="TikTok Wireless Earbuds",
        keywords=["bluetooth", "anc"],
        pdp_url="https://shop.tiktok.com/view/product/99999",
    )
    conn.close()

    # Reopen database (simulate process restart)
    conn2 = connect(db_file)
    repo2 = WorkflowRepository(conn2)
    engine2 = WorkflowEngine(repo2)
    topic_handlers = create_product_video_topic_handlers(
        workflow_engine=engine2, workflow_repository=repo2, provider_mode="fake"
    )

    outbox_repo = OutboxRepository(conn2)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="worker-prod-1")
    report = dispatcher.process_batch()

    assert report.claimed == 1
    assert report.succeeded == 1
    assert outbox_repo.list_unacknowledged() == []

    # Verify latest_artifact was persisted to workflow aggregate
    agg, version = repo2.get_workflow(wf_id)
    assert "latest_artifact" in agg
    assert agg["latest_artifact"]["owner"] == "product_intelligence"
    assert version == 2

    conn2.close()


def test_runtime_durable_worker_processes_happy_path(tmp_path):
    """Test run_worker runtime composition (automatic topic handler binding) in a thread."""
    import threading, time

    db_file = tmp_path / "worker_runtime.db"
    conn = connect(db_file)

    repo = WorkflowRepository(conn)
    wf_id = "wf_worker_01"
    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="TikTok Smart Watch",
        keywords=["fitness", "heart_rate"],
    )
    conn.close()

    stop_evt = threading.Event()
    worker_thread = threading.Thread(
        target=run_worker,
        kwargs={"db_path": db_file, "poll_interval": 0.05, "stop_event": stop_evt, "provider_mode": "fake"},
        daemon=True,
    )
    worker_thread.start()

    # Wait for durable_worker to process outbox
    time.sleep(0.3)
    stop_evt.set()
    worker_thread.join(timeout=2.0)

    # Reopen to verify outbox ACKed and state persisted
    verify_conn = connect(db_file)
    outbox_repo = OutboxRepository(verify_conn)
    assert outbox_repo.list_unacknowledged() == []

    repo_verify = WorkflowRepository(verify_conn)
    agg, _ = repo_verify.get_workflow(wf_id)
    assert agg.get("latest_artifact", {}).get("owner") == "product_intelligence"
    verify_conn.close()


def test_user_entrypoint_operator_command_starts_and_advances_workflow(tmp_path):
    """Test user entry point POST /api/operator/command starts workflow, advances to HITL gate,
    and operator approval advances workflow to next stage."""
    from hermes_personal.contracts.operator import OperatorCommand, PrincipalContext
    from hermes_personal.application.operator_handler import create_operator_command_handler
    from hermes_personal.application.events_api import EventsAPI

    db_file = tmp_path / "operator_entry.db"
    conn = connect(db_file)
    handler = create_operator_command_handler(conn, provider_mode="fake")
    api = EventsAPI(command_handler=handler, auth_validator=lambda token, owner: True)

    wf_id = "wf_entry_01"
    principal = PrincipalContext(actor_id="alice", owner_user_id="alice", channel="web", session_id="s1")

    # 1. User Entry Point: start_workflow via operator command
    cmd_start = OperatorCommand(
        principal=principal,
        command_type="start_workflow",
        target_id=wf_id,
        expected_version=0,
        payload={"product_name": "ANC Headphones", "keywords": ["noise_canceling", "bass"]},
    )
    status_code, resp = api.handle_operator_command(
        auth_token="valid_token",
        owner_id="alice",
        command_type="start_workflow",
        target_id=wf_id,
        expected_version=0,
        payload={"product_name": "ANC Headphones", "keywords": ["noise_canceling", "bass"]},
    )
    assert status_code == 200
    assert resp["status"] == "ok"
    assert resp["result"]["status"] == "started"

    # 2. Worker processes outbox message for product_video.research in explicit fake mode
    repo = WorkflowRepository(conn)
    topic_handlers = create_product_video_topic_handlers(workflow_repository=repo, provider_mode="fake")
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="worker-op-1")

    report = dispatcher.process_batch()
    assert report.claimed == 1
    assert report.succeeded == 1
    assert outbox_repo.list_unacknowledged() == []

    # 3. Assert workflow reached HITL gate AwaitingProductLock & approval request created
    agg, version = repo.get_workflow(wf_id)
    assert agg["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    assert "pending_approval_id" in agg

    appr_svc = ApprovalService(conn)
    req = appr_svc.get_request(agg["pending_approval_id"])
    assert req.status.value == "pending"

    # 4. User Entry Point: approve operator command to advance workflow
    status_code_appr, resp_appr = api.handle_operator_command(
        auth_token="valid_token",
        owner_id="alice",
        command_type="approve",
        target_id=req.request_id,
        expected_version=version,
    )
    assert status_code_appr == 200
    assert resp_appr["result"]["status"] == "approved"
    assert resp_appr["result"]["new_state"] == ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value
    assert resp_appr["result"]["enqueued_job"] == "product_video.resource_pack"

    # 5. Process next stage outbox messages (product_video.resource_pack -> product_video.lock)
    report2 = dispatcher.process_batch()
    assert report2.claimed == 1
    assert report2.succeeded == 1

    report3 = dispatcher.process_batch()
    assert report3.claimed == 1
    assert report3.succeeded == 1

    agg2, _ = repo.get_workflow(wf_id)
    assert agg2["state"] == ProductVideoWorkflowState.CREATING_BRIEF.value
    conn.close()


def test_unconfigured_provider_mode_configured_fails_without_ack(tmp_path):
    """Test that default provider_mode='configured' fails closed and does NOT ACK outbox work."""
    db_file = tmp_path / "missing_config.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_unconfig_01"

    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Product X",
        keywords=["k1"],
    )

    # Handlers initialized with default provider_mode='configured' (missing live API clients)
    topic_handlers = create_product_video_topic_handlers(workflow_repository=repo, provider_mode="configured")
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="worker-cfg-1")

    report = dispatcher.process_batch()
    # Expect failure because live provider is unconfigured in 'configured' mode
    assert report.claimed == 1
    assert report.failed == 1
    assert report.succeeded == 0
    # Outbox message MUST NOT be ACKed!
    assert len(outbox_repo.list_unacknowledged()) == 1
    conn.close()


def test_e2e_http_operator_route_full_workflow_progression(tmp_path):
    """Full end-to-end HTTP route integration test using TestClient(app) progressing through all workflow stages."""
    db_file = tmp_path / "e2e_http.db"
    conn = connect(db_file)
    cmd_handler = create_operator_command_handler(conn, provider_mode="fake")
    events_api = EventsAPI(
        command_handler=cmd_handler,
        auth_validator=lambda token, owner: token == "valid_token" and owner == "alice",
    )
    app = create_application(events_api=events_api)
    client = TestClient(app)

    repo = WorkflowRepository(conn)
    topic_handlers = create_product_video_topic_handlers(workflow_repository=repo, provider_mode="fake")
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="e2e-http-worker")

    wf_id = "wf_e2e_http"
    headers = {"Authorization": "Bearer valid_token"}

    # Step 1: POST /api/operator/command (start_workflow)
    resp1 = client.post(
        "/api/operator/command",
        headers=headers,
        json={
            "owner_id": "alice",
            "command_type": "start_workflow",
            "target_id": wf_id,
            "expected_version": 0,
            "payload": {"product_name": "Earbuds", "keywords": ["anc"]},
        },
    )
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert body1["status"] == "ok"
    assert body1["result"]["status"] == "started"
    assert body1["result"]["workflow_id"] == wf_id

    agg1, ver1 = repo.get_workflow(wf_id)
    assert agg1["state"] == ProductVideoWorkflowState.RESEARCHING.value
    assert ver1 == 1

    # Step 2: Run dispatcher.process_batch() for product_video.research
    report2 = dispatcher.process_batch()
    assert report2.claimed == 1
    assert report2.succeeded == 1

    agg2, ver2 = repo.get_workflow(wf_id)
    assert agg2["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    assert "pending_approval_id" in agg2
    req_id_1 = agg2["pending_approval_id"]
    assert agg2["latest_artifact"]["owner"] == "product_intelligence"
    assert ver2 == 2

    # Step 3: POST /api/operator/command (approve req_id_1)
    resp3 = client.post(
        "/api/operator/command",
        headers=headers,
        json={
            "owner_id": "alice",
            "command_type": "approve",
            "target_id": req_id_1,
            "expected_version": ver2,
            "payload": {"expected_version": ver2},
        },
    )
    assert resp3.status_code == 200
    body3 = resp3.json()
    assert body3["status"] == "ok"
    assert body3["result"]["status"] == "approved"
    assert body3["result"]["new_state"] == ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value
    assert body3["result"]["enqueued_job"] == "product_video.resource_pack"

    agg3, ver3 = repo.get_workflow(wf_id)
    assert agg3["state"] == ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value
    assert ver3 == 3

    # Step 4: Run dispatcher for product_video.resource_pack -> enqueues product_video.lock, then run dispatcher for product_video.lock -> CREATING_BRIEF
    report4a = dispatcher.process_batch()
    assert report4a.claimed == 1
    assert report4a.succeeded == 1

    agg4a, ver4a = repo.get_workflow(wf_id)
    assert agg4a["state"] == ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value
    assert ver4a == 4

    report4b = dispatcher.process_batch()
    assert report4b.claimed == 1
    assert report4b.succeeded == 1

    agg4b, ver4b = repo.get_workflow(wf_id)
    assert agg4b["state"] == ProductVideoWorkflowState.CREATING_BRIEF.value
    assert ver4b == 5

    # Step 5: Run dispatcher.process_batch() for product_video.creative_brief -> AwaitingBriefApproval
    report5 = dispatcher.process_batch()
    assert report5.claimed == 1
    assert report5.succeeded == 1

    agg5, ver5 = repo.get_workflow(wf_id)
    assert agg5["state"] == ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value
    assert "pending_approval_id" in agg5
    req_id_2 = agg5["pending_approval_id"]
    assert "latest_artifact" in agg5
    assert ver5 == 6

    # Step 6: POST /api/operator/command (approve req_id_2) -> scene_plan job -> AwaitingSceneApproval
    resp6 = client.post(
        "/api/operator/command",
        headers=headers,
        json={
            "owner_id": "alice",
            "command_type": "approve",
            "target_id": req_id_2,
            "expected_version": ver5,
            "payload": {"expected_version": ver5},
        },
    )
    assert resp6.status_code == 200
    assert resp6.json()["result"]["new_state"] == ProductVideoWorkflowState.CREATING_SCENE_PLAN.value
    assert resp6.json()["result"]["enqueued_job"] == "product_video.scene_plan"

    report6_job = dispatcher.process_batch()
    assert report6_job.claimed == 1
    assert report6_job.succeeded == 1

    agg6, ver6 = repo.get_workflow(wf_id)
    assert agg6["state"] == ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL.value
    assert "pending_approval_id" in agg6
    req_id_3 = agg6["pending_approval_id"]
    assert "latest_artifact" in agg6
    assert ver6 == 8

    # Step 7: POST /api/operator/command (approve req_id_3) -> storyboard job -> AwaitingStoryboardApproval
    resp7 = client.post(
        "/api/operator/command",
        headers=headers,
        json={
            "owner_id": "alice",
            "command_type": "approve",
            "target_id": req_id_3,
            "expected_version": ver6,
            "payload": {"expected_version": ver6},
        },
    )
    assert resp7.status_code == 200
    assert resp7.json()["result"]["new_state"] == ProductVideoWorkflowState.CREATING_STORYBOARD.value
    assert resp7.json()["result"]["enqueued_job"] == "product_video.storyboard"

    report7_job = dispatcher.process_batch()
    assert report7_job.claimed == 1
    assert report7_job.succeeded == 1

    agg7, ver7 = repo.get_workflow(wf_id)
    assert agg7["state"] == ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value
    assert "pending_approval_id" in agg7
    req_id_4 = agg7["pending_approval_id"]
    assert "latest_artifact" in agg7
    assert ver7 == 10

    # Step 8: POST /api/operator/command (approve req_id_4) -> render job -> AwaitingFinalApproval
    resp8 = client.post(
        "/api/operator/command",
        headers=headers,
        json={
            "owner_id": "alice",
            "command_type": "approve",
            "target_id": req_id_4,
            "expected_version": ver7,
            "payload": {"expected_version": ver7},
        },
    )
    assert resp8.status_code == 200
    assert resp8.json()["result"]["new_state"] == ProductVideoWorkflowState.RENDERING.value
    assert resp8.json()["result"]["enqueued_job"] == "product_video.render"

    report8_job = dispatcher.process_batch()
    assert report8_job.claimed == 1
    assert report8_job.succeeded == 1

    agg8, ver8 = repo.get_workflow(wf_id)
    assert agg8["state"] == ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL.value
    assert "pending_approval_id" in agg8
    req_id_5 = agg8["pending_approval_id"]
    assert "latest_artifact" in agg8
    assert ver8 == 12

    # Step 9: POST /api/operator/command (approve req_id_5) -> export job -> COMPLETED!
    resp9 = client.post(
        "/api/operator/command",
        headers=headers,
        json={
            "owner_id": "alice",
            "command_type": "approve",
            "target_id": req_id_5,
            "expected_version": ver8,
            "payload": {"expected_version": ver8},
        },
    )
    assert resp9.status_code == 200
    assert resp9.json()["result"]["new_state"] == ProductVideoWorkflowState.EXPORTING.value
    assert resp9.json()["result"]["enqueued_job"] == "product_video.export"

    report9_job = dispatcher.process_batch()
    assert report9_job.claimed == 1
    assert report9_job.succeeded == 1

    agg9, ver9 = repo.get_workflow(wf_id)
    assert agg9["state"] == ProductVideoWorkflowState.COMPLETED.value
    assert "latest_artifact" in agg9
    assert ver9 == 14
    conn.close()


def test_stale_expected_version_rejected_without_db_mutation(tmp_path):
    """Test that commit_workflow with a stale expected_version raises VersionConflict,
    and submitting an approve command with a stale expected_version returns an error
    without mutating the database state or approval request.
    """
    from hermes_personal.workflows.repository import VersionConflict

    db_file = tmp_path / "stale_version.db"
    conn = connect(db_file)
    cmd_handler = create_operator_command_handler(conn, provider_mode="fake")
    events_api = EventsAPI(
        command_handler=cmd_handler,
        auth_validator=lambda token, owner: token == "valid_token" and owner == "alice",
    )
    app = create_application(events_api=events_api)
    client = TestClient(app)

    repo = WorkflowRepository(conn)
    topic_handlers = create_product_video_topic_handlers(workflow_repository=repo, provider_mode="fake")
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="stale-worker")

    wf_id = "wf_stale_01"
    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Smart Ring",
        keywords=["health"],
    )
    dispatcher.process_batch()

    agg_before, version_before = repo.get_workflow(wf_id)
    assert agg_before["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    req_id = agg_before["pending_approval_id"]

    # 1. Direct repository test: stale expected_version raises VersionConflict
    with pytest.raises(VersionConflict):
        repo.commit_workflow(
            workflow_id=wf_id,
            aggregate_json=json.dumps({"state": "invalid_mutation"}),
            events=[],
            expected_version=999,
        )

    # Assert repository state remains unmutated
    agg_mid, version_mid = repo.get_workflow(wf_id)
    assert agg_mid["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    assert version_mid == version_before

    # 2. HTTP route test: approve command with stale expected_version is rejected with HTTP 400
    resp = client.post(
        "/api/operator/command",
        headers={"Authorization": "Bearer valid_token"},
        json={
            "owner_id": "alice",
            "command_type": "approve",
            "target_id": req_id,
            "expected_version": 999,
            "payload": {"expected_version": 999},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "command_failed"
    assert "Stale workflow version" in resp.json()["message"]

    # Assert database state remains unmutated (approval is still pending, state is awaiting)
    appr_svc = ApprovalService(conn)
    assert appr_svc.get_request(req_id).status.value == "pending"
    agg_after, version_after = repo.get_workflow(wf_id)
    assert agg_after["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    assert version_after == version_before
    conn.close()


def test_transaction_rollback_on_commit_failure(tmp_path):
    """Test that if repo.commit_workflow raises an error during approve_and_advance_workflow,
    the single atomic SQLite transaction rolls back completely: approval status remains 'pending',
    aggregate state remains unchanged, and no outbox message is written.
    """
    db_file = tmp_path / "rollback.db"
    conn = connect(db_file)
    cmd_handler = create_operator_command_handler(conn, provider_mode="fake")
    events_api = EventsAPI(
        command_handler=cmd_handler,
        auth_validator=lambda token, owner: token == "valid_token" and owner == "alice",
    )
    app = create_application(events_api=events_api)
    client = TestClient(app)

    repo = WorkflowRepository(conn)
    topic_handlers = create_product_video_topic_handlers(workflow_repository=repo, provider_mode="fake")
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="rollback-worker")

    wf_id = "wf_rollback_01"
    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Smart Glasses",
        keywords=["ai", "ar"],
    )
    dispatcher.process_batch()

    agg_before, ver_before = repo.get_workflow(wf_id)
    assert agg_before["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    req_id = agg_before["pending_approval_id"]
    approval_svc = ApprovalService(conn)
    assert approval_svc.get_request(req_id).status.value == "pending"

    def failing_commit_workflow(*args, **kwargs):
        raise RuntimeError("Simulated Commit Failure")

    # Inject failure into WorkflowRepository.commit_workflow on class level during approval processing
    with patch.object(WorkflowRepository, "commit_workflow", side_effect=failing_commit_workflow):
        resp = client.post(
            "/api/operator/command",
            headers={"Authorization": "Bearer valid_token"},
            json={
                "owner_id": "alice",
                "command_type": "approve",
                "target_id": req_id,
                "expected_version": ver_before,
                "payload": {"expected_version": ver_before},
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "command_failed"

    # Assert transaction rolled back completely: approval remains pending, state unchanged, outbox empty
    assert approval_svc.get_request(req_id).status.value == "pending"
    agg_after, ver_after = repo.get_workflow(wf_id)
    assert agg_after["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    assert ver_after == ver_before
    assert outbox_repo.list_unacknowledged() == []
    conn.close()


def test_repeated_approval_does_not_duplicate_job(tmp_path):
    """Test that approving an already approved request raises ValueError
    and does NOT enqueue duplicate outbox jobs.
    """
    db_file = tmp_path / "repeat_approval.db"
    conn = connect(db_file)
    cmd_handler = create_operator_command_handler(conn, provider_mode="fake")
    events_api = EventsAPI(
        command_handler=cmd_handler,
        auth_validator=lambda token, owner: token == "valid_token" and owner == "alice",
    )
    app = create_application(events_api=events_api)
    client = TestClient(app)

    repo = WorkflowRepository(conn)
    topic_handlers = create_product_video_topic_handlers(workflow_repository=repo, provider_mode="fake")
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="repeat-worker")

    wf_id = "wf_repeat_01"
    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Wireless Speaker",
        keywords=["audio"],
    )
    dispatcher.process_batch()

    agg, version = repo.get_workflow(wf_id)
    req_id = agg["pending_approval_id"]

    # 1. First approval via POST /api/operator/command succeeds
    res1 = client.post(
        "/api/operator/command",
        headers={"Authorization": "Bearer valid_token"},
        json={
            "owner_id": "alice",
            "command_type": "approve",
            "target_id": req_id,
            "expected_version": version,
            "payload": {"expected_version": version},
        },
    )
    assert res1.status_code == 200
    assert res1.json()["result"]["status"] == "approved"

    outbox_after_first = outbox_repo.list_unacknowledged()
    assert len(outbox_after_first) == 1

    # 2. Repeated approval directly via ApprovalService raises ValueError
    appr_svc = ApprovalService(conn)
    with pytest.raises(ValueError, match="already|APPROVED"):
        appr_svc.approve(req_id)

    # 3. Repeated approval via POST /api/operator/command returns 400 error
    res2 = client.post(
        "/api/operator/command",
        headers={"Authorization": "Bearer valid_token"},
        json={
            "owner_id": "alice",
            "command_type": "approve",
            "target_id": req_id,
            "expected_version": version,
            "payload": {"expected_version": version},
        },
    )
    assert res2.status_code == 400
    assert res2.json()["error"] == "command_failed"

    # 4. Outbox MUST NOT contain any duplicate jobs
    outbox_after_second = outbox_repo.list_unacknowledged()
    assert len(outbox_after_second) == 1
    assert outbox_after_second[0].outbox_id == outbox_after_first[0].outbox_id
    conn.close()
