import json
import sqlite3

import pytest

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
    topic_handlers = create_product_video_topic_handlers(workflow_engine=engine2, workflow_repository=repo2)

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
        kwargs={"db_path": db_file, "poll_interval": 0.05, "stop_event": stop_evt},
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
