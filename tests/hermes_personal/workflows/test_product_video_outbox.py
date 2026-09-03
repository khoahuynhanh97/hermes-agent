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
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))
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
    if report5.succeeded != 1:
        print("DEBUG report5:", report5)
        cur = conn.cursor()
        cur.execute('SELECT outbox_id, last_error FROM workflow_outbox ORDER BY outbox_id DESC LIMIT 3')
        for row in cur.fetchall():
            print("DEBUG outbox row:", row[0], "err=", (row[1] or '')[:800])
    assert report5.succeeded == 1, report5

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


def test_approval_request_mismatch_rejected_without_db_mutation(tmp_path):
    """FIX 1: Test that an approval request that is pending but NOT the current pending request
    for the workflow aggregate is rejected without mutating DB state, approval status, or outbox.
    """
    db_file = tmp_path / "appr_mismatch.db"
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
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="mismatch-worker")

    wf_id = "wf_mismatch_01"
    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Smart Ring",
        keywords=["health"],
    )
    dispatcher.process_batch()

    agg_before, ver_before = repo.get_workflow(wf_id)
    canonical_req_id = agg_before["pending_approval_id"]

    # Submit an orphan/stale pending approval request directly to ApprovalService
    appr_svc = ApprovalService(conn)
    stale_req_id = appr_svc.submit_request({
        "workflow_id": wf_id,
        "gate": "AwaitingProductLock",
        "workflow_version": ver_before,
    })

    # Attempt to approve the stale_req_id (which is not agg_before["pending_approval_id"])
    resp = client.post(
        "/api/operator/command",
        headers={"Authorization": "Bearer valid_token"},
        json={
            "owner_id": "alice",
            "command_type": "approve",
            "target_id": stale_req_id,
            "expected_version": ver_before,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "command_failed"
    assert "mismatch" in resp.json()["message"].lower() or "does not match" in resp.json()["message"].lower()

    # Verify DB state, canonical approval request, and outbox remain completely unmutated
    agg_after, ver_after = repo.get_workflow(wf_id)
    assert agg_after["pending_approval_id"] == canonical_req_id
    assert agg_after["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    assert ver_after == ver_before
    assert appr_svc.get_request(canonical_req_id).status.value == "pending"
    assert outbox_repo.list_unacknowledged() == []
    conn.close()


def test_job_completion_hitl_approval_creation_rollback_on_persistence_failure(tmp_path):
    """FIX 2: Test that if repo.commit_workflow raises an exception during job completion,
    the HITL approval request creation and aggregate update roll back atomically together,
    leaving zero approval orphans in a fresh SQLite connection.
    """
    db_file = tmp_path / "creation_rollback.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_create_rollback_01"

    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Drone Camera",
        keywords=["4k", "flight"],
    )

    topic_handlers = create_product_video_topic_handlers(workflow_repository=repo, provider_mode="fake")
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="rollback-create-worker")

    # Inject failure during commit_workflow
    def failing_commit_workflow(*args, **kwargs):
        raise RuntimeError("Simulated Persistence Failure on Job Completion")

    with patch.object(WorkflowRepository, "commit_workflow", side_effect=failing_commit_workflow):
        report = dispatcher.process_batch()
        assert report.failed == 1

    conn.close()

    # Reopen fresh connection to verify zero orphan approval records exist
    fresh_conn = connect(db_file)
    fresh_repo = WorkflowRepository(fresh_conn)
    fresh_appr_svc = ApprovalService(fresh_conn)

    agg, ver = fresh_repo.get_workflow(wf_id)
    assert agg["state"] == ProductVideoWorkflowState.RESEARCHING.value
    assert "pending_approval_id" not in agg

    # Query approval_request table directly: MUST be completely empty (0 rows)
    cur = fresh_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM approval_request")
    assert cur.fetchone()[0] == 0
    fresh_conn.close()


def test_provider_boundary_spy_receives_product_identity_and_locked_resource_pack(tmp_path):
    """FIX 3: Test that VideoFactoryClient receives the exact product identity (product_id)
    and locked resource pack payload at the provider boundary.
    """
    from hermes_personal.application.operator_handler import approve_and_advance_workflow
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine
    from hermes_personal.integrations.video_factory.client import VideoFactoryClient

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    db_file = tmp_path / "provider_spy.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_spy_01"

    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Smart Watch Ultra",
        keywords=["fitness", "gps"],
    )

    recorded_calls = []

    class SpyVideoFactoryClient(VideoFactoryClient):
        def create_creative_brief(self, product_id=None, brief_config=None, **kwargs):
            recorded_calls.append({
                "product_id": product_id,
                "brief_config": brief_config,
                "kwargs": kwargs,
            })
            return super().create_creative_brief(product_id=product_id, brief_config=brief_config, **kwargs)

    spy_client = SpyVideoFactoryClient()
    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        video_client=spy_client,
        provider_mode="fake",
    )
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="spy-worker")

    # Step 1: research -> AwaitingProductLock
    rep1 = dispatcher.process_batch()
    assert rep1.succeeded == 1

    # Step 2: approve AwaitingProductLock via approve_and_advance_workflow -> enqueues resource_pack
    agg, ver = repo.get_workflow(wf_id)
    approve_and_advance_workflow(conn, agg["pending_approval_id"], expected_version=ver)

    # Advance state: resource_pack -> lock -> creative_brief -> AwaitingBriefApproval
    rep2 = dispatcher.process_batch()  # resource_pack -> enqueues lock
    assert rep2.succeeded == 1, f"rep2 failed: {rep2}"

    rep3 = dispatcher.process_batch()  # lock -> enqueues creative_brief
    assert rep3.succeeded == 1, f"rep3 failed: {rep3}"

    agg_locked, _ = repo.get_workflow(wf_id)
    locked_pack = agg_locked.get("latest_artifact")
    assert locked_pack is not None

    rep4 = dispatcher.process_batch()  # creative_brief -> AwaitingBriefApproval
    assert rep4.succeeded == 1, f"rep4 failed: {rep4}"

    # Assert VideoFactoryClient received the exact product_id and locked resource pack!
    assert len(recorded_calls) == 1
    brief_call = recorded_calls[0]
    assert brief_call["product_id"] == locked_pack.get("resource_pack_id")
    assert brief_call["brief_config"]["resource_pack"] == locked_pack
    conn.close()


def test_approve_and_advance_workflow_resolves_workflow_id_without_wf_prefix(tmp_path):
    """Test that approve_and_advance_workflow resolves workflow ID without 'wf_' prefix."""
    from hermes_personal.application.operator_handler import approve_and_advance_workflow

    db_file = tmp_path / "prefix_test.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "custom_video_pipeline_42"

    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Action Camera",
        keywords=["4k", "waterproof"],
    )

    topic_handlers = create_product_video_topic_handlers(workflow_repository=repo, provider_mode="fake")
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="prefix-worker")

    rep1 = dispatcher.process_batch()
    assert rep1.succeeded == 1

    agg, ver = repo.get_workflow(wf_id)
    assert agg["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    assert "pending_approval_id" in agg

    # Pass the workflow_id directly (which has NO wf_ prefix) instead of approval request id
    res = approve_and_advance_workflow(conn, wf_id, expected_version=ver)
    assert res["status"] == "approved"
    assert res["workflow_id"] == wf_id
    assert res["new_state"] == ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value

    # Non-existent target_id raises KeyError
    with pytest.raises(KeyError, match="not found"):
        approve_and_advance_workflow(conn, "completely_unknown_id")

    # Workflow without pending approval raises KeyError
    with pytest.raises(KeyError, match="No pending approval"):
        approve_and_advance_workflow(conn, wf_id)

    conn.close()


def test_configured_mode_with_real_mcp_response_shapes_and_polling(tmp_path):
    """Test that provider_mode='configured' properly decodes real MCP response shapes across
    the entire 14-state workflow, 5 HITL gates, and handles async render polling and export.
    """
    from tools.registry import ToolRegistry
    from hermes_personal.application.operator_handler import approve_and_advance_workflow
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    db_file = tmp_path / "configured_mcp_real.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_mcp_real_01"

    real_registry = ToolRegistry()
    called_tools = []

    # Tool 1: Research returning standard MCP CallToolResult content block
    def mcp_research_handler(args):
        called_tools.append(("research", args))
        assert "keywords" not in args
        assert "pdp_url" not in args
        query = args.get("query", "")
        assert isinstance(query, str)
        assert "query" not in args or isinstance(query, str)
        return json.dumps({
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "product_name": args.get("product_name"),
                    "query": query,
                    "url": args.get("url"),
                    "report": json.dumps({"pdp_url": "https://example.com/pdp", "specs": "4K 60fps"}),
                    "snapshot_id": "snap_ext_001",
                    "persistence_status": "persisted",
                    "canonical_product_id": "prod_ext_drone",
                    "media_assets": [{"asset_id": "asset_ext_1", "local_path": "/data/media/ext_1.jpg", "match_status": "matched", "product_match_score": 0.9, "usage_policy": "approved"}],
                    "id": "ext_mcp_pi_001",
                })
            }],
            "isError": False,
        })

    # Tool 2: Resource pack builder - strict signature contract
    def mcp_build_pack_handler(args):
        called_tools.append(("build_pack", args))
        assert "research_result" not in args
        assert "keywords" not in args
        assert "pack_dict" not in args
        assert args.get("snapshot_id") in {"snap_ext_001", "snap_failed"}
        pack_id = f"rp_{args.get('snapshot_id')}"
        payload = {
            "status": "built",
            "resource_pack_id": pack_id,
            "pack_status": "ready_to_lock",
            "canonical_product_id": "prod_ext_drone",
            "variant_id": args.get("variant_id"),
            "summary": "Strict contract resource pack",
            "media_count": 1,
            "claims": [{"text": "Strict identity verified", "status": "verified"}],
            "restrictions": [],
            "completeness": {"has_images": True, "has_specs": True},
            "assets_mapping": {"asset_01": "/data/media/strict.jpg"},
            "scene_plan": ["intro", "features", "outro"],
        }
        if args.get("snapshot_id") == "snap_failed":
            return json.dumps({"status": "not_found", "snapshot_id": "snap_failed"})
        return json.dumps(payload)

    # Tool 3: Lock resource pack tool - strict signature contract
    def mcp_lock_pack_handler(args):
        called_tools.append(("lock_pack", args))
        assert "pack_dict" not in args
        assert "snapshot_id" not in args
        assert args.get("resource_pack_id") == "rp_snap_ext_001"
        assert args.get("owner_user_id") is not None
        return json.dumps({
            "structuredContent": {
                "owner": "product_intelligence",
                "schema": "product_resource_pack_locked",
                "version": 1,
                "lock_id": "lock_rp_snap_ext_001",
                "resource_pack_id": "rp_snap_ext_001",
                "snapshot_id": "snap_ext_001",
                "canonical_product_id": "prod_ext_drone",
                "owner_user_id": args.get("owner_user_id"),
                "manifest_digest": "sha256:ext_digest_001",
                "created_at": "2026-08-28T12:00:00Z",
                "status": "locked",
                "summary": "Strict contract resource pack",
                "assets": [{"asset_id": "asset_01", "local_path": "/data/media/strict.jpg"}],
                "assets_mapping": {"asset_01": "/data/media/strict.jpg"},
                "scene_plan": ["intro", "features", "outro"],
                "id": "ext_lock_001",
            }
        })

    # Tool 4: Creative brief
    def mcp_brief_handler(args):
        called_tools.append(("brief", args))
        return json.dumps({
            "result": json.dumps({
                "brief_id": f"brief_{args.get('product_id')}",
                "product_id": args.get("product_id"),
                "script": "High performance 4K drone script",
                "angle": "Tech / Feature Showcase",
                "id": "ext_brief_002",
            })
        })

    # Tool 5: Scene plan
    def mcp_scene_plan_handler(args):
        called_tools.append(("scene_plan", args))
        return json.dumps({
            "result": json.dumps({
                "scene_plan_id": "scene_plan_mcp_003",
                "scenes": [
                    {"scene_id": "s1", "duration": 5, "description": "Drone takeoff"},
                    {"scene_id": "s2", "duration": 10, "description": "4K camera specs"},
                ],
                "id": "ext_scene_003",
            })
        })

    # Tool 6: Storyboard
    def mcp_storyboard_handler(args):
        called_tools.append(("storyboard", args))
        return json.dumps({
            "structuredContent": {
                "storyboard_id": "sb_mcp_004",
                "frames": [
                    {"frame_id": "f1", "visual": "drone_air.jpg", "caption": "Clear 4K View"},
                ],
                "id": "ext_sb_004",
            }
        })

    # Tool 7: Render returning async pending job
    render_poll_count = 0
    def mcp_render_handler(args):
        called_tools.append(("render", args))
        return json.dumps({
            "result": json.dumps({
                "status": "pending",
                "job_id": "gpu_job_777",
            })
        })

    # Tool 8: Polling tool for render status
    def mcp_poll_status_handler(args):
        nonlocal render_poll_count
        render_poll_count += 1
        called_tools.append(("poll_status", args))
        return json.dumps({
            "result": json.dumps({
                "status": "completed",
                "job_id": args.get("job_id"),
                "render_id": "render_mcp_completed_888",
                "video_url": "https://cdn.example.com/final_render.mp4",
            })
        })

    # Tool 9: Export tool
    def mcp_export_handler(args):
        called_tools.append(("export", args))
        return json.dumps({
            "structuredContent": {
                "export_id": "export_mcp_999",
                "final_video_url": "https://cdn.example.com/final_export_1080p.mp4",
            }
        })

    real_registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, mcp_research_handler)
    real_registry.register("mcp__product_intelligence__build_resource_pack", "mcp-pi", {}, mcp_build_pack_handler)
    real_registry.register("mcp__product_intelligence__lock_resource_pack", "mcp-pi", {}, mcp_lock_pack_handler)
    real_registry.register("mcp__video_factory__create_brief", "mcp-vf", {}, mcp_brief_handler)
    real_registry.register("mcp__video_factory__create_scene_plan", "mcp-vf", {}, mcp_scene_plan_handler)
    real_registry.register("mcp__video_factory__create_storyboard", "mcp-vf", {}, mcp_storyboard_handler)
    real_registry.register("mcp__video_factory__render", "mcp-vf", {}, mcp_render_handler)
    real_registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, mcp_poll_status_handler)
    real_registry.register("mcp__video_factory__export", "mcp-vf", {}, mcp_export_handler)

    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Drone Pro 4K",
        keywords=["gimbal", "4k"],
    )

    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=real_registry,
        provider_mode="configured",
        poll_timeout=10.0,
        poll_interval=0.1,
    )
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="real-mcp-worker")

    # Step 1: research -> AwaitingProductLock
    rep1 = dispatcher.process_batch()
    assert rep1.succeeded == 1
    agg, ver = repo.get_workflow(wf_id)
    assert agg["state"] == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
    assert agg["latest_artifact"]["external_provider_id"] == "ext_mcp_pi_001"

    # Step 2: approve AwaitingProductLock -> resource_pack -> lock -> creative_brief -> AwaitingBriefApproval
    approve_and_advance_workflow(conn, agg["pending_approval_id"], expected_version=ver)
    rep2 = dispatcher.process_batch()  # resource_pack -> enqueues lock
    assert rep2.succeeded == 1
    rep3 = dispatcher.process_batch()  # lock -> enqueues brief
    assert rep3.succeeded == 1
    rep4 = dispatcher.process_batch()  # brief -> AwaitingBriefApproval
    assert rep4.succeeded == 1

    agg_brief, ver_brief = repo.get_workflow(wf_id)
    assert agg_brief["state"] == ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value
    assert agg_brief["latest_artifact"]["product_id"] == "rp_snap_ext_001"

    # Step 3: approve AwaitingBriefApproval -> scene_plan -> AwaitingSceneApproval
    approve_and_advance_workflow(conn, agg_brief["pending_approval_id"], expected_version=ver_brief)
    rep5 = dispatcher.process_batch()  # scene_plan -> AwaitingSceneApproval
    assert rep5.succeeded == 1

    agg_scene, ver_scene = repo.get_workflow(wf_id)
    assert agg_scene["state"] == ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL.value
    assert agg_scene["latest_artifact"]["scene_plan_id"] == "scene_plan_mcp_003"

    # Step 4: approve AwaitingSceneApproval -> storyboard -> AwaitingStoryboardApproval
    approve_and_advance_workflow(conn, agg_scene["pending_approval_id"], expected_version=ver_scene)
    rep6 = dispatcher.process_batch()  # storyboard -> AwaitingStoryboardApproval
    assert rep6.succeeded == 1

    agg_sb, ver_sb = repo.get_workflow(wf_id)
    assert agg_sb["state"] == ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value
    assert agg_sb["latest_artifact"]["storyboard_id"] == "sb_mcp_004"

    # Step 5: approve AwaitingStoryboardApproval -> render (async pending + poll status) -> AwaitingFinalApproval
    approve_and_advance_workflow(conn, agg_sb["pending_approval_id"], expected_version=ver_sb)
    rep7 = dispatcher.process_batch()  # render -> polls get_job_status -> AwaitingFinalApproval
    assert rep7.succeeded == 1
    assert render_poll_count >= 1

    agg_render, ver_render = repo.get_workflow(wf_id)
    assert agg_render["state"] == ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL.value
    assert agg_render["latest_artifact"]["video_url"] == "https://cdn.example.com/final_render.mp4"

    # Step 6: approve AwaitingFinalApproval -> export -> COMPLETED
    approve_and_advance_workflow(conn, agg_render["pending_approval_id"], expected_version=ver_render)
    rep8 = dispatcher.process_batch()  # export -> COMPLETED
    assert rep8.succeeded == 1

    agg_final, _ = repo.get_workflow(wf_id)
    assert agg_final["state"] == ProductVideoWorkflowState.COMPLETED.value
    assert agg_final["latest_artifact"]["final_video_url"] == "https://cdn.example.com/final_export_1080p.mp4"

    # Verify all tools were exercised
    tool_types_called = [t[0] for t in called_tools]
    assert "research" in tool_types_called
    assert "build_pack" in tool_types_called
    assert "brief" in tool_types_called
    assert "scene_plan" in tool_types_called
    assert "storyboard" in tool_types_called
    assert "render" in tool_types_called
    assert "poll_status" in tool_types_called
    assert "export" in tool_types_called

    conn.close()


def test_configured_mode_missing_resource_pack_tool_fails_closed_without_mock_assets(tmp_path):
    """Test that provider_mode='configured' fails closed when resource_pack build tool is missing
    without generating mock assets or fake fallback data.
    """
    from hermes_personal.application.operator_handler import approve_and_advance_workflow

    db_file = tmp_path / "missing_pack.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_no_pack_01"

    # Research and video tools are registered, but build_resource_pack is missing
    partial_calls = []

    def strict_research_handler(args):
        partial_calls.append(("research", args))
        assert "keywords" not in args
        assert "pdp_url" not in args
        return {
            "product_name": args.get("product_name"),
            "query": args.get("query"),
            "url": args.get("url"),
            "report": json.dumps({"pdp_url": "https://example.com"}),
            "snapshot_id": "snap_partial_001",
            "persistence_status": "persisted",
            "canonical_product_id": "prod_partial_001",
            "media_assets": [{"asset_id": "asset_partial_1", "local_path": "/data/media/partial_1.jpg", "match_status": "matched", "product_match_score": 0.9, "usage_policy": "approved"}],
            "id": "ext_pi_partial_001",
        }

    partial_registry = {
        "mcp__product_intelligence__research_product": strict_research_handler,
        "mcp__video_factory__create_brief": lambda p: {"brief_id": "b1", "product_id": p.get("product_id")},
    }

    start_product_video_workflow(
        workflow_repository=repo,
        workflow_id=wf_id,
        product_name="Smart Mug",
        keywords=["heating"],
    )

    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=partial_registry,
        provider_mode="configured",
    )
    outbox_repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="fail-worker")

    # Step 1: research succeeds
    dispatcher.process_batch()
    agg, ver = repo.get_workflow(wf_id)

    # Step 2: approve AwaitingProductLock -> dispatches resource_pack
    approve_and_advance_workflow(conn, agg["pending_approval_id"], expected_version=ver)

    # Step 3: resource_pack MUST fail closed because tool is not registered
    rep = dispatcher.process_batch()
    assert rep.failed == 1
    assert rep.succeeded == 0

    unack = outbox_repo.list_unacknowledged()
    assert len(unack) == 1
    assert "MISSING_PROVIDER_CONFIG" in unack[0].last_error
    assert "product.resource_pack.build" in unack[0].last_error

    conn.close()


def test_configured_mode_render_pending_without_polling_tool_fails_closed(tmp_path):
    """Test that render returning pending status without a polling tool fails closed."""
    from hermes_personal.product_video.handlers import MCPVideoFactoryAdapter

    registry_without_polling = {
        "mcp__video_factory__render": lambda p: {"status": "pending", "job_id": "gpu_async_999"},
    }

    adapter = MCPVideoFactoryAdapter(registry_without_polling, {"render": "mcp__video_factory__render"})
    with pytest.raises(RuntimeError, match="no status polling tool"):
        adapter.render_video({"storyboard_id": "sb_1"})


def test_configured_mode_export_missing_output_fails_closed():
    """Test that export returning empty output fails closed without creating success artifact."""
    from hermes_personal.product_video.handlers import MCPVideoFactoryAdapter

    registry_with_empty_export = {
        "mcp__video_factory__export": lambda p: {"status": "success"},  # Missing final_video_url/export_id
    }

    adapter = MCPVideoFactoryAdapter(registry_with_empty_export, {"export": "mcp__video_factory__export"})
    with pytest.raises(RuntimeError, match="missing required final output reference"):
        adapter.export_video({"render_id": "render_1"})


def test_mcp_error_payload_raises_runtime_error():
    """Test that MCP isError/is_error payload raises descriptive RuntimeError."""
    from hermes_personal.product_video.handlers import _decode_mcp_output

    error_response = {
        "isError": True,
        "content": [{"type": "text", "text": "CUDA device out of memory (OOM)"}],
    }
    with pytest.raises(RuntimeError, match="CUDA device out of memory"):
        _decode_mcp_output(error_response)


def test_wrapped_error_in_result_string_fails_closed():
    """Test that wrapped error inside a JSON result string raises RuntimeError."""
    from hermes_personal.product_video.handlers import _decode_mcp_output

    wrapped_error = {
        "result": json.dumps({"status": "failed", "error": "Rate limit exceeded (429)"}),
    }
    with pytest.raises(RuntimeError, match="Rate limit exceeded"):
        _decode_mcp_output(wrapped_error)


def test_wrapped_error_in_structured_content_fails_closed():
    """Test that wrapped error inside structuredContent raises RuntimeError."""
    from hermes_personal.product_video.handlers import _decode_mcp_output

    wrapped_error = {
        "structuredContent": {"error": "Invalid API token", "code": "UNAUTHORIZED"},
    }
    with pytest.raises(RuntimeError, match="Invalid API token"):
        _decode_mcp_output(wrapped_error)


def test_creative_brief_empty_content_fails_closed():
    """Test that creative brief tool returning empty output fails closed."""
    from hermes_personal.product_video.handlers import MCPVideoFactoryAdapter

    registry_empty_brief = {
        "mcp__video_factory__create_brief": lambda p: {"unrelated_field": "data"},
    }
    adapter = MCPVideoFactoryAdapter(registry_empty_brief, {"brief": "mcp__video_factory__create_brief"})
    with pytest.raises(RuntimeError, match="empty creative brief content"):
        adapter.create_creative_brief("prod_1", {})


def test_failed_render_with_id_fails_closed():
    """Test that render returning failed status even with an ID raises RuntimeError."""
    from hermes_personal.product_video.handlers import MCPVideoFactoryAdapter

    registry_failed_render = {
        "mcp__video_factory__render": lambda p: {"status": "failed", "job_id": "job_123", "error": "GPU kernel crash"},
    }
    adapter = MCPVideoFactoryAdapter(registry_failed_render, {"render": "mcp__video_factory__render"})
    with pytest.raises(RuntimeError, match="GPU kernel crash"):
        adapter.render_video({"storyboard_id": "sb_1"})

    registry_failed_no_error_field = {
        "mcp__video_factory__render": lambda p: {"status": "failed", "job_id": "job_456"},
    }
    adapter2 = MCPVideoFactoryAdapter(registry_failed_no_error_field, {"render": "mcp__video_factory__render"})
    with pytest.raises(RuntimeError, match="status 'failed'"):
        adapter2.render_video({"storyboard_id": "sb_1"})


def test_worker_bootstrap_with_config_yaml_and_env(tmp_path, monkeypatch):
    """Test worker startup configuration resolution from config.yaml and .env with temp HERMES_HOME."""
    import yaml
    from hermes_personal.workflows.worker import main

    home = tmp_path / "hermes_home"
    home.mkdir()
    config_file = home / "config.yaml"
    env_file = home / ".env"

    config_data = {
        "provider_mode": "fake",
        "video_factory": {
            "polling_timeout_seconds": 120.0,
            "polling_interval_seconds": 1.5,
        },
    }
    config_file.write_text(yaml.safe_dump(config_data), encoding="utf-8")
    env_file.write_text("HERMES_API_KEY=test_secret_key\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(home))
    db_file = str(home / "test_worker.db")

    # Run worker with poll-interval 0.01 and immediately exit via mocked signal
    executed = []
    def mock_run_worker(**kwargs):
        executed.append(kwargs)

    monkeypatch.setattr("hermes_personal.workflows.worker.run_worker", mock_run_worker)

    exit_code = main(["--db-path", db_file])
    assert exit_code == 0
    assert len(executed) == 1
    assert executed[0]["provider_mode"] == "fake"
    assert executed[0]["render_poll_timeout"] == 120.0
    assert executed[0]["render_poll_interval"] == 1.5


def test_job_polling_timeout_does_not_resubmit_and_resumes_same_job_id(tmp_path):
    """Test Fix 1: Provider accepts render job -> timeout -> next attempt resumes polling same job_id (submit_count=1)."""
    from tools.registry import ToolRegistry
    from hermes_personal.application.operator_handler import approve_and_advance_workflow

    db_file = tmp_path / "resume_job.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_resume_01"

    submit_count = 0
    poll_calls = []

    def mock_render(payload):
        nonlocal submit_count
        submit_count += 1
        return json.dumps({"status": "pending", "job_id": "gpu_paid_job_555"})

    poll_phase = "timeout"
    def mock_poll(payload):
        poll_calls.append(payload.get("job_id"))
        if poll_phase == "timeout":
            return json.dumps({"status": "pending", "job_id": payload.get("job_id")})
        return json.dumps({
            "status": "completed",
            "job_id": payload.get("job_id"),
            "video_url": "https://cdn.example.com/resumed_video.mp4",
        })

    registry = ToolRegistry()
    registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, lambda p: json.dumps({"report": "ok"}))
    registry.register("mcp__video_factory__render", "mcp-vf", {}, mock_render)
    registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, mock_poll)

    # Seed workflow in RENDERING state
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RENDERING.value}),
        events=[{"event_id": "evt_1", "command_id": "cmd_1", "event_type": "WorkflowStarted", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_render_1",
            payload={"job_name": "product_video.render", "workflow_id": wf_id, "args": [{"storyboard_id": "sb_1"}]},
        ),
    )

    outbox_repo = OutboxRepository(conn)
    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=0.2,
        poll_interval=0.05,
    )
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="w-resume")

    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    # Attempt 1: Submits job (submit_count=1) -> polls -> times out -> failure recorded
    rep1 = dispatcher.process_batch()
    assert rep1.failed == 1
    assert rep1.succeeded == 0
    assert submit_count == 1
    assert "gpu_paid_job_555" in poll_calls

    # Verify active_render_job_id is preserved on workflow aggregate
    agg_after_timeout, _ = repo.get_workflow(wf_id)
    assert agg_after_timeout.get("active_render_job_id") == "gpu_paid_job_555"

    # Reset outbox row next_attempt_at for immediate retry
    conn.execute("UPDATE workflow_outbox SET next_attempt_at = NULL WHERE workflow_id = ?", (wf_id,))
    conn.commit()

    # Attempt 2: Switch polling to succeed. Must RESUME polling same job_id WITHOUT re-submitting to provider!
    poll_phase = "ready"
    rep2 = dispatcher.process_batch()
    assert rep2.succeeded == 1
    assert submit_count == 1  # Still 1! No blind re-submission of paid job!
    assert poll_calls[-1] == "gpu_paid_job_555"

    agg_final, _ = repo.get_workflow(wf_id)
    assert agg_final["state"] == ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL.value
    assert agg_final["latest_artifact"]["video_url"] == "https://cdn.example.com/resumed_video.mp4"
    assert "active_render_job_id" not in agg_final  # Cleared after success

    conn.close()


def test_outbox_extend_lease_heartbeat_and_scaled_lease_duration(tmp_path):
    """Test Fix 2: extend_lease atomic extension and scaled lease coverage for long jobs."""
    db_file = tmp_path / "lease_test.db"
    conn = connect(db_file)
    repo = OutboxRepository(conn)

    msg = repo.enqueue("wf_lease_01", "test payload")
    claims = repo.claim("worker_1", lease_duration_seconds=10.0, now_iso="2026-01-01T10:00:00+00:00")
    assert len(claims) == 1
    claim = claims[0]
    assert claim.lease_expires_at == "2026-01-01T10:00:10+00:00"

    # Extend lease at t=5s by 60s
    success = repo.extend_lease(claim.outbox_id, claim.lease_token, "worker_1", extension_seconds=60.0, now_iso="2026-01-01T10:00:05+00:00")
    assert success is True

    # At t=15s (original lease would have expired), ACK still succeeds because lease was extended
    ack_success = repo.ack(claim.outbox_id, claim.lease_token, "worker_1", now_iso="2026-01-01T10:00:15+00:00")
    assert ack_success is True

    conn.close()


def test_invalid_provider_mode_and_polling_settings_fail_closed():
    """Test Fix 3: Strict validation fails closed on invalid provider_mode and polling settings."""
    from hermes_personal.product_video.handlers import (
        ProductVideoJobHandlers,
        create_product_video_topic_handlers,
        validate_provider_mode,
        validate_polling_setting,
    )
    from hermes_personal.workflows.worker import run_worker

    # Invalid provider modes
    with pytest.raises(ValueError, match="Invalid provider_mode"):
        validate_provider_mode("auto")

    with pytest.raises(ValueError, match="Invalid provider_mode"):
        validate_provider_mode("mock")

    with pytest.raises(ValueError, match="Invalid provider_mode type"):
        validate_provider_mode(123)

    with pytest.raises(ValueError, match="Invalid provider_mode"):
        ProductVideoJobHandlers(provider_mode="invalid")

    with pytest.raises(ValueError, match="Invalid provider_mode"):
        create_product_video_topic_handlers(provider_mode="unsupported")

    # Invalid polling settings
    with pytest.raises(ValueError, match="finite and > 0"):
        validate_polling_setting("poll_timeout", -5.0, 60.0)

    with pytest.raises(ValueError, match="finite and > 0"):
        validate_polling_setting("poll_timeout", 0.0, 60.0)

    with pytest.raises(ValueError, match="finite and > 0"):
        validate_polling_setting("poll_timeout", float("nan"), 60.0)

    with pytest.raises(ValueError, match="finite and > 0"):
        validate_polling_setting("poll_timeout", float("inf"), 60.0)

    with pytest.raises(ValueError, match="type bool"):
        validate_polling_setting("poll_timeout", True, 60.0)


def test_job_accepted_persisted_to_db_before_first_poll(tmp_path):
    """Test Requirement 1: Provider job_id is saved to SQLite immediately on acceptance before first poll."""
    from tools.registry import ToolRegistry
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    db_file = tmp_path / "checkpoint_test.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_check_01"

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    checked_in_db_before_poll = False

    def mock_render(payload):
        return json.dumps({"status": "pending", "job_id": "gpu_live_999"})

    def mock_poll(payload):
        nonlocal checked_in_db_before_poll
        # Check SQLite from a distinct connection right on the first poll
        reader_conn = connect(db_file)
        reader_repo = WorkflowRepository(reader_conn)
        data = reader_repo.get_workflow(wf_id)
        if data and data[0].get("active_render_job_id") == "gpu_live_999":
            checked_in_db_before_poll = True
        reader_conn.close()
        return json.dumps({"status": "completed", "job_id": "gpu_live_999", "video_url": "https://cdn.example.com/live.mp4"})

    registry = ToolRegistry()
    registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, lambda p: json.dumps({"report": "ok"}))
    registry.register("mcp__video_factory__render", "mcp-vf", {}, mock_render)
    registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, mock_poll)

    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RENDERING.value}),
        events=[{"event_id": "evt_1", "command_id": "cmd_1", "event_type": "WorkflowStarted", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_chk_1",
            payload={"job_name": "product_video.render", "workflow_id": wf_id, "args": [{"storyboard_id": "sb_1"}]},
        ),
    )

    outbox_repo = OutboxRepository(conn)
    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=1.0,
        poll_interval=0.01,
    )
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="w-chk")

    rep = dispatcher.process_batch()
    assert rep.succeeded == 1
    assert checked_in_db_before_poll is True, "provider job_id was NOT in DB before first poll was executed!"

    conn.close()


def test_poll_network_exception_without_job_id_recovers_and_resumes_same_job_id(tmp_path):
    """Test Requirement 1: Network exception with no job_id text in error message still resumes same job_id on restart."""
    from tools.registry import ToolRegistry
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    db_file = tmp_path / "net_err_test.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_net_01"

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    submit_count = 0
    poll_mode = "net_error"

    def mock_render(payload):
        nonlocal submit_count
        submit_count += 1
        return json.dumps({"status": "pending", "job_id": "gpu_resilient_777"})

    def mock_poll(payload):
        if poll_mode == "net_error":
            # Network drop - generic error containing zero job_id text
            raise ConnectionResetError("Connection dropped by remote server 504")
        return json.dumps({"status": "completed", "job_id": payload.get("job_id"), "video_url": "https://cdn.example.com/recovered.mp4"})

    registry = ToolRegistry()
    registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, lambda p: json.dumps({"report": "ok"}))
    registry.register("mcp__video_factory__render", "mcp-vf", {}, mock_render)
    registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, mock_poll)

    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RENDERING.value}),
        events=[{"event_id": "evt_1", "command_id": "cmd_1", "event_type": "WorkflowStarted", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_net_1",
            payload={"job_name": "product_video.render", "workflow_id": wf_id, "args": [{"storyboard_id": "sb_1"}]},
        ),
    )

    outbox_repo = OutboxRepository(conn)
    topic_handlers1 = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=0.5,
        poll_interval=0.01,
    )
    dispatcher1 = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers1, worker_id="w-net-1")

    # Attempt 1: Submits job -> poll network drop -> failure recorded
    rep1 = dispatcher1.process_batch()
    assert rep1.failed == 1
    assert submit_count == 1

    # Simulate process restart: create completely fresh repository and dispatcher instances
    conn2 = connect(db_file)
    repo2 = WorkflowRepository(conn2)
    outbox_repo2 = OutboxRepository(conn2)
    conn2.execute("UPDATE workflow_outbox SET next_attempt_at = NULL WHERE workflow_id = ?", (wf_id,))
    conn2.commit()

    poll_mode = "recovered"
    topic_handlers2 = create_product_video_topic_handlers(
        workflow_repository=repo2,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=0.5,
        poll_interval=0.01,
    )
    dispatcher2 = OutboxDispatcher(outbox_repo2, topic_handlers=topic_handlers2, worker_id="w-net-2")

    # Attempt 2 after restart: must resume polling gpu_resilient_777 WITHOUT calling render tool again
    rep2 = dispatcher2.process_batch()
    assert rep2.succeeded == 1
    assert submit_count == 1, "Render tool was called again after restart instead of resuming polling!"

    agg, _ = repo2.get_workflow(wf_id)
    assert agg["state"] == ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL.value
    assert agg["latest_artifact"]["video_url"] == "https://cdn.example.com/recovered.mp4"

    conn.close()
    conn2.close()


def test_checkpoint_commit_failure_after_accept_quarantines_and_prevents_resubmit_on_restart(tmp_path):
    """Test 1: Checkpoint persistence failure after accept immediately quarantines outbox row, halting resubmit on restart."""
    from tools.registry import ToolRegistry
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    db_file = tmp_path / "chk_fail.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_chk_fail_01"

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    submit_count = 0

    def mock_render(payload):
        nonlocal submit_count
        submit_count += 1
        return json.dumps({"status": "pending", "job_id": "paid_gpu_job_001"})

    registry = ToolRegistry()
    registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, lambda p: json.dumps({"report": "ok"}))
    registry.register("mcp__video_factory__render", "mcp-vf", {}, mock_render)
    registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, lambda p: json.dumps({"status": "completed"}))

    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RENDERING.value}),
        events=[{"event_id": "evt_1", "command_id": "cmd_1", "event_type": "WorkflowStarted", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_chk_fail_1",
            payload={"job_name": "product_video.render", "workflow_id": wf_id, "args": [{"storyboard_id": "sb_1"}]},
        ),
    )

    # Monkeypatch commit_workflow during checkpoint to simulate database I/O error
    orig_commit = repo.commit_workflow
    def broken_commit_workflow(*args, **kwargs):
        if "active_render_job_id" in kwargs.get("aggregate_json", ""):
            raise sqlite3.OperationalError("disk I/O error during checkpoint commit")
        return orig_commit(*args, **kwargs)

    repo.commit_workflow = broken_commit_workflow  # type: ignore

    outbox_repo = OutboxRepository(conn)
    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=1.0,
        poll_interval=0.01,
    )
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="w-chk-fail")

    rep1 = dispatcher.process_batch()
    assert rep1.quarantined == 1
    assert rep1.succeeded == 0
    assert submit_count == 1

    # Verify SQLite row is in quarantined state with next_attempt_at NULL
    cur = conn.execute("SELECT state, next_attempt_at, last_error FROM workflow_outbox WHERE workflow_id = ?", (wf_id,))
    row = cur.fetchone()
    assert row["state"] == "quarantined"
    assert row["next_attempt_at"] is None
    assert "CHECKPOINT_PERSISTENCE_FAILED" in row["last_error"]

    # Simulate subsequent worker batch and restart: quarantined row CANNOT be claimed
    rep2 = dispatcher.process_batch()
    assert rep2.claimed == 0
    assert rep2.succeeded == 0
    assert submit_count == 1  # No duplicate submission!

    conn2 = connect(db_file)
    outbox_repo2 = OutboxRepository(conn2)
    dispatcher2 = OutboxDispatcher(outbox_repo2, topic_handlers=topic_handlers, worker_id="w-chk-fail-2")
    rep3 = dispatcher2.process_batch()
    assert rep3.claimed == 0
    assert rep3.succeeded == 0
    assert submit_count == 1  # Still 1 on restart!

    conn.close()
    conn2.close()


def test_terminal_provider_response_quarantines_and_no_resubmit_in_subsequent_batches(tmp_path):
    """Test 2: Terminal provider response (failed/cancelled) directly quarantines outbox message and never resubmits."""
    from tools.registry import ToolRegistry
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    db_file = tmp_path / "terminal_quarantine.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_term_quar_01"

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    submit_count = 0

    def mock_render(payload):
        nonlocal submit_count
        submit_count += 1
        return json.dumps({"status": "pending", "job_id": "gpu_fail_002"})

    def mock_poll(payload):
        return json.dumps({"status": "failed", "error": "Model runtime corrupted"})

    registry = ToolRegistry()
    registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, lambda p: json.dumps({"report": "ok"}))
    registry.register("mcp__video_factory__render", "mcp-vf", {}, mock_render)
    registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, mock_poll)

    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RENDERING.value}),
        events=[{"event_id": "evt_1", "command_id": "cmd_1", "event_type": "WorkflowStarted", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_term_quar_1",
            payload={"job_name": "product_video.render", "workflow_id": wf_id, "args": [{"storyboard_id": "sb_1"}]},
        ),
    )

    outbox_repo = OutboxRepository(conn)
    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=0.5,
        poll_interval=0.01,
    )
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="w-term-quar")

    rep1 = dispatcher.process_batch()
    assert rep1.quarantined == 1
    assert rep1.succeeded == 0
    assert submit_count == 1

    cur = conn.execute("SELECT state, next_attempt_at, last_error FROM workflow_outbox WHERE workflow_id = ?", (wf_id,))
    row = cur.fetchone()
    assert row["state"] == "quarantined"
    assert row["next_attempt_at"] is None
    assert "Model runtime corrupted" in row["last_error"]

    # Run 3 subsequent batches: message is never claimed again and provider is never called again
    for _ in range(3):
        rep = dispatcher.process_batch()
        assert rep.claimed == 0
        assert rep.succeeded == 0
        assert submit_count == 1

    conn.close()


def test_handler_with_side_effect_raising_typeerror_invoked_exactly_once(tmp_path):
    """Test 3: If handler body executes side-effects and raises TypeError, it is NOT invoked a second time."""
    from hermes_personal.workflows.envelope import OutboxEnvelope

    db_file = tmp_path / "type_err.db"
    conn = connect(db_file)
    outbox_repo = OutboxRepository(conn)

    invocation_count = 0

    def faulty_handler(envelope: OutboxEnvelope, heartbeat_fn=None):
        nonlocal invocation_count
        invocation_count += 1
        # Side-effect then raise internal TypeError
        raise TypeError("Simulated internal TypeError inside handler business logic")

    envelope_msg = build_envelope(
        workflow_id="wf_type_01",
        topic="job.dispatch",
        idempotency_key="idemp_type_1",
        payload={"job_name": "custom.job"},
    )
    outbox_repo.enqueue("wf_type_01", envelope_msg)

    dispatcher = OutboxDispatcher(
        outbox_repo,
        topic_handlers={"job.dispatch": faulty_handler},
        worker_id="w-type-err",
    )

    rep = dispatcher.process_batch()
    assert rep.failed == 1
    assert invocation_count == 1, f"Handler was invoked {invocation_count} times instead of exactly 1!"

    conn.close()


def test_lease_renewal_does_not_decrease_existing_expiry(tmp_path):
    """Test 4: extend_lease guarantees renewal NEVER reduces the current lease_expires_at."""
    db_file = tmp_path / "lease_expiry.db"
    conn = connect(db_file)
    repo = OutboxRepository(conn)

    repo.enqueue("wf_lease_exp_01", "msg payload")
    # Claim with a 120s lease at t0
    t0 = "2026-01-01T12:00:00+00:00"
    claims = repo.claim("w-exp", lease_duration_seconds=120.0, now_iso=t0)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.lease_expires_at == "2026-01-01T12:02:00+00:00"

    # At t0 + 10s, attempt extend_lease with short extension 30s (candidate = 12:00:40 < 12:02:00)
    t1 = "2026-01-01T12:00:10+00:00"
    success = repo.extend_lease(claim.outbox_id, claim.lease_token, "w-exp", extension_seconds=30.0, now_iso=t1)
    assert success is True

    cur = conn.execute("SELECT lease_expires_at FROM workflow_outbox WHERE outbox_id = ?", (claim.outbox_id,))
    row = cur.fetchone()
    # Must STILL be 12:02:00 (not reduced to 12:00:40!)
    assert row["lease_expires_at"] == "2026-01-01T12:02:00+00:00"

    # Now attempt extend_lease with extension 200s (candidate = 12:03:30 > 12:02:00)
    success2 = repo.extend_lease(claim.outbox_id, claim.lease_token, "w-exp", extension_seconds=200.0, now_iso=t1)
    assert success2 is True
    cur = conn.execute("SELECT lease_expires_at FROM workflow_outbox WHERE outbox_id = ?", (claim.outbox_id,))
    row = cur.fetchone()
    # Now it increases to 12:03:30
    assert row["lease_expires_at"] == "2026-01-01T12:03:30+00:00"

    conn.close()


def test_runtime_polling_advances_past_initial_lease_with_real_heartbeat_renewal(tmp_path, monkeypatch):
    """Test 5: Polling exceeding initial lease duration extends lease dynamically and ACKs cleanly."""
    from datetime import datetime, timezone
    from tools.registry import ToolRegistry
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    db_file = tmp_path / "long_poll.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_long_poll_01"

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    # Fake clock progression:
    # t0 = 1767268800.0 (2026-01-01T12:00:00+00:00)
    # Initial lease: 10.0s -> initial expiry: 2026-01-01T12:00:10+00:00
    # Poll 1 at t=12:00:04 -> extends lease by 60s (to 12:01:04)
    # Poll 2 at t=12:00:08 -> extends lease by 60s (to 12:01:08)
    # Poll 3 at t=12:00:12 -> extends lease by 60s (to 12:01:12) (t=12:00:12 strictly > initial expiry 12:00:10)
    # Final ACK at t=12:00:12 -> succeeds because 12:01:12 > 12:00:12
    current_fake_time = [1767268800.0]  # 2026-01-01T12:00:00+00:00

    def fake_time():
        return current_fake_time[0]

    def fake_now_iso(now_iso: str | None = None) -> str:
        if now_iso is not None:
            return now_iso
        return datetime.fromtimestamp(current_fake_time[0], tz=timezone.utc).isoformat()

    monkeypatch.setattr("time.time", fake_time)
    monkeypatch.setattr("time.monotonic", fake_time)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("hermes_personal.workflows.outbox_repository._now_iso", fake_now_iso)

    poll_count = 0
    observed_expirations = []

    def mock_render(payload):
        return json.dumps({"status": "pending", "job_id": "gpu_long_01"})

    def mock_poll(payload):
        nonlocal poll_count
        poll_count += 1
        # Advance fake time by 4.0 seconds on each poll
        current_fake_time[0] += 4.0

        reader = connect(db_file)
        cur = reader.execute("SELECT lease_expires_at FROM workflow_outbox WHERE workflow_id = ?", (wf_id,))
        row = cur.fetchone()
        if row and row["lease_expires_at"]:
            observed_expirations.append(row["lease_expires_at"])
        reader.close()

        if poll_count < 3:
            return json.dumps({"status": "pending", "job_id": "gpu_long_01"})
        return json.dumps({"status": "completed", "job_id": "gpu_long_01", "video_url": "https://cdn.example.com/long.mp4"})

    registry = ToolRegistry()
    registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, lambda p: json.dumps({"report": "ok"}))
    registry.register("mcp__video_factory__render", "mcp-vf", {}, mock_render)
    registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, mock_poll)

    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RENDERING.value}),
        events=[{"event_id": "evt_1", "command_id": "cmd_1", "event_type": "WorkflowStarted", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_long_poll_1",
            payload={"job_name": "product_video.render", "workflow_id": wf_id, "args": [{"storyboard_id": "sb_1"}]},
        ),
    )

    outbox_repo = OutboxRepository(conn)

    # Spy on claim to capture initial claim expiry
    orig_claim = outbox_repo.claim
    captured_claims = []

    def spy_claim(*args, **kwargs):
        claims = orig_claim(*args, **kwargs)
        if claims and not captured_claims:
            captured_claims.append(claims[0])
        return claims

    outbox_repo.claim = spy_claim

    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=60.0,
        poll_interval=0.001,
    )
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="w-long", lease_duration_seconds=10.0)

    rep = dispatcher.process_batch()

    # 1. Assert initial claim expiry was exactly T0 + 10s
    assert len(captured_claims) == 1
    initial_claim_expiry = captured_claims[0].lease_expires_at
    assert initial_claim_expiry == "2026-01-01T12:00:10+00:00"

    # 2. Assert that clock advanced deterministically past initial expiry (T0 + 12s > T0 + 10s)
    clock_at_ack_iso = datetime.fromtimestamp(current_fake_time[0], tz=timezone.utc).isoformat()
    assert current_fake_time[0] == 1767268812.0
    assert clock_at_ack_iso > initial_claim_expiry

    # 3. Assert renewed SQLite expiry is greater than initial expiry and greater than the clock at final ACK
    assert len(observed_expirations) == 3
    latest_renewed_expiry = observed_expirations[-1]
    assert latest_renewed_expiry == "2026-01-01T12:01:08+00:00"
    assert latest_renewed_expiry > initial_claim_expiry
    assert latest_renewed_expiry > clock_at_ack_iso

    # 4. Assert successful dispatch and clean outbox row deletion
    assert rep.succeeded == 1
    assert rep.stale == 0
    cur = conn.execute("SELECT COUNT(*) as cnt FROM workflow_outbox WHERE workflow_id = ?", (wf_id,))
    assert cur.fetchone()["cnt"] == 0

    conn.close()


def test_runtime_polling_without_renewal_expires_and_fails_ack(tmp_path, monkeypatch):
    """Test 5b (Negative Control): Without heartbeat lease renewal, time passing initial expiry causes stale ACK."""
    from datetime import datetime, timezone
    from tools.registry import ToolRegistry
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    db_file = tmp_path / "neg_long_poll.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_neg_poll_01"

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    current_fake_time = [1767268800.0]  # 2026-01-01T12:00:00+00:00

    def fake_time():
        return current_fake_time[0]

    def fake_now_iso(now_iso: str | None = None) -> str:
        if now_iso is not None:
            return now_iso
        return datetime.fromtimestamp(current_fake_time[0], tz=timezone.utc).isoformat()

    monkeypatch.setattr("time.time", fake_time)
    monkeypatch.setattr("time.monotonic", fake_time)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("hermes_personal.workflows.outbox_repository._now_iso", fake_now_iso)

    poll_count = 0

    def mock_render(payload):
        return json.dumps({"status": "pending", "job_id": "gpu_neg_01"})

    def mock_poll(payload):
        nonlocal poll_count
        poll_count += 1
        # Advance clock past initial 10s lease (4s + 4s + 4s = 12s elapsed)
        current_fake_time[0] += 4.0
        if poll_count < 3:
            return json.dumps({"status": "pending", "job_id": "gpu_neg_01"})
        return json.dumps({"status": "completed", "job_id": "gpu_neg_01", "video_url": "https://cdn.example.com/neg.mp4"})

    registry = ToolRegistry()
    registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, lambda p: json.dumps({"report": "ok"}))
    registry.register("mcp__video_factory__render", "mcp-vf", {}, mock_render)
    registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, mock_poll)

    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RENDERING.value}),
        events=[{"event_id": "evt_1", "command_id": "cmd_1", "event_type": "WorkflowStarted", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_neg_poll_1",
            payload={"job_name": "product_video.render", "workflow_id": wf_id, "args": [{"storyboard_id": "sb_1"}]},
        ),
    )

    outbox_repo = OutboxRepository(conn)
    # Negative control: heartbeat returns True but does NOT extend lease in SQLite
    outbox_repo.extend_lease = lambda *args, **kwargs: True  # type: ignore

    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=60.0,
        poll_interval=0.001,
    )
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="w-neg", lease_duration_seconds=10.0)

    rep = dispatcher.process_batch()

    # Initial lease expired (12:00:10 < 12:00:12) -> ACK fails as stale!
    assert rep.succeeded == 0
    assert rep.stale == 1

    # Outbox message was NOT deleted (retained in SQLite)
    cur = conn.execute("SELECT COUNT(*) as cnt FROM workflow_outbox WHERE workflow_id = ?", (wf_id,))
    assert cur.fetchone()["cnt"] == 1

    conn.close()


def test_heartbeat_failure_stops_execution_without_committing_success(tmp_path):
    """Test 6: Lease lost (heartbeat returns False) raises LeaseLostError and halts without committing success."""
    from tools.registry import ToolRegistry
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    db_file = tmp_path / "lease_lost.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_lease_lost_01"

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    registry = ToolRegistry()
    registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, lambda p: json.dumps({"report": "ok"}))
    registry.register("mcp__video_factory__render", "mcp-vf", {}, lambda p: json.dumps({"status": "pending", "job_id": "gpu_lost_01"}))
    registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, lambda p: json.dumps({"status": "completed", "job_id": "gpu_lost_01", "video_url": "https://cdn.example.com/lost.mp4"}))

    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RENDERING.value}),
        events=[{"event_id": "evt_1", "command_id": "cmd_1", "event_type": "WorkflowStarted", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_lost_1",
            payload={"job_name": "product_video.render", "workflow_id": wf_id, "args": [{"storyboard_id": "sb_1"}]},
        ),
    )

    handlers_service = ProductVideoJobHandlers(
        workflow_repository=repo,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=1.0,
        poll_interval=0.01,
    )
    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        handlers_service=handlers_service,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=1.0,
        poll_interval=0.01,
    )

    outbox_repo = OutboxRepository(conn)
    # Monkeypatch repository.extend_lease to return False (lease lost)
    outbox_repo.extend_lease = lambda *args, **kwargs: False  # type: ignore

    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="w-lost")

    rep = dispatcher.process_batch()
    assert rep.succeeded == 0
    assert rep.quarantined == 1

    # Workflow aggregate must NOT have reached final approval
    agg, _ = repo.get_workflow(wf_id)
    assert agg["state"] == ProductVideoWorkflowState.RENDERING.value

    conn.close()


def test_heartbeat_exception_raises_lease_lost_and_quarantines(tmp_path):
    """Test 6b: Heartbeat raising an exception is normalized to LeaseLostError, halting execution and quarantining."""
    from tools.registry import ToolRegistry
    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine

    db_file = tmp_path / "hb_exc.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_id = "wf_hb_exc_01"

    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

    registry = ToolRegistry()
    registry.register("mcp__product_intelligence__research_product", "mcp-pi", {}, lambda p: json.dumps({"report": "ok"}))
    registry.register("mcp__video_factory__render", "mcp-vf", {}, lambda p: json.dumps({"status": "pending", "job_id": "gpu_exc_01"}))
    registry.register("mcp__video_factory__get_job_status", "mcp-vf", {}, lambda p: json.dumps({"status": "completed", "job_id": "gpu_exc_01", "video_url": "https://cdn.example.com/exc.mp4"}))

    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RENDERING.value}),
        events=[{"event_id": "evt_1", "command_id": "cmd_1", "event_type": "WorkflowStarted", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}],
        outbox_message=build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key="idemp_hb_exc_1",
            payload={"job_name": "product_video.render", "workflow_id": wf_id, "args": [{"storyboard_id": "sb_1"}]},
        ),
    )

    outbox_repo = OutboxRepository(conn)
    # Monkeypatch repository.extend_lease to raise an OperationalError (e.g. database network loss)
    def broken_extend_lease(*args, **kwargs):
        raise sqlite3.OperationalError("database locked during heartbeat")

    outbox_repo.extend_lease = broken_extend_lease  # type: ignore

    topic_handlers = create_product_video_topic_handlers(
        workflow_repository=repo,
        tool_registry=registry,
        provider_mode="configured",
        poll_timeout=1.0,
        poll_interval=0.01,
    )
    dispatcher = OutboxDispatcher(outbox_repo, topic_handlers=topic_handlers, worker_id="w-hb-exc")

    rep = dispatcher.process_batch()
    assert rep.succeeded == 0
    assert rep.quarantined == 1

    # Workflow aggregate must NOT have completed
    agg, _ = repo.get_workflow(wf_id)
    assert agg["state"] == ProductVideoWorkflowState.RENDERING.value

    conn.close()


def test_direct_run_worker_and_resolve_provider_mode_rejects_falsy_inputs(tmp_path):
    """Test 7: Direct run_worker and resolve_provider_mode fail closed on False, 0, empty string."""
    from hermes_personal.workflows.worker import run_worker
    from hermes_personal.product_video.handlers import resolve_provider_mode

    db_file = tmp_path / "falsy.db"

    # run_worker directly
    with pytest.raises(ValueError, match="Invalid provider_mode type bool"):
        run_worker(db_path=db_file, provider_mode=False)

    with pytest.raises(ValueError, match="Invalid provider_mode type int"):
        run_worker(db_path=db_file, provider_mode=0)

    with pytest.raises(ValueError, match="empty string"):
        run_worker(db_path=db_file, provider_mode="")

    with pytest.raises(ValueError, match="empty string"):
        run_worker(db_path=db_file, provider_mode="   ")

    # resolve_provider_mode
    with pytest.raises(ValueError, match="Invalid provider_mode type bool"):
        resolve_provider_mode(cli_arg=False)

    with pytest.raises(ValueError, match="Invalid provider_mode type bool"):
        resolve_provider_mode(config={"provider_mode": False})

    with pytest.raises(ValueError, match="Invalid provider_mode type bool"):
        resolve_provider_mode(config={"workflows": {"provider_mode": False}})

    with pytest.raises(ValueError, match="Invalid provider_mode type int"):
        resolve_provider_mode(cli_arg=0)

    with pytest.raises(ValueError, match="Invalid provider_mode type int"):
        resolve_provider_mode(config={"provider_mode": 0})

    with pytest.raises(ValueError, match="empty string"):
        resolve_provider_mode(cli_arg="")

    with pytest.raises(ValueError, match="empty string"):
        resolve_provider_mode(config={"provider_mode": ""})

    with pytest.raises(ValueError, match="empty string"):
        resolve_provider_mode(config={"provider_mode": "   "})

    with pytest.raises(ValueError, match="empty string"):
        resolve_provider_mode(env_val="")

    # Valid values resolve properly
    assert resolve_provider_mode(cli_arg="fake") == "fake"
    assert resolve_provider_mode(config={"provider_mode": "configured"}) == "configured"
    assert resolve_provider_mode(config={"workflows": {"provider_mode": "fake"}}) == "fake"
    assert resolve_provider_mode(env_val="fake") == "fake"
    assert resolve_provider_mode() == "configured"
