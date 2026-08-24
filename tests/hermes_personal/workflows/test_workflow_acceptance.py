import sqlite3
import pytest
from hermes_personal.storage.sqlite import SCHEMA
from hermes_personal.workflows.definitions import DEFINITIONS
from hermes_personal.workflows.engine import WorkflowEngine


from hermes_personal.workflows.repository import WorkflowRepository
from hermes_personal.workflows.approvals import ApprovalService, ApprovalStatus
from hermes_personal.workflows.budgets import BudgetEngine, BudgetPolicy
from hermes_personal.workflows.jobs import JobDispatcher, JobSpec, JobStatus
from hermes_personal.workflows.recovery import WorkflowRecoveryService

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    yield conn
    conn.close()


def test_phase4_exit_criterion_1_typed_workflow_definitions():
    p2v = DEFINITIONS["product_to_video"]
    assert p2v.name == "product_to_video"
    assert "video_production" in p2v.required_artifacts

    kl = DEFINITIONS["knowledge_learning"]
    assert kl.name == "knowledge_learning"
    assert "synthesizing" in kl.states

def test_phase4_exit_criterion_2_idempotent_command_engine(db_conn):
    repo = WorkflowRepository(db_conn)
    engine = WorkflowEngine(repo)

    cmd = {
        "command_id": "cmd-1",
        "workflow_id": "wf-1",
        "type": "start",
        "args": {"definition_name": "product_to_video"}
    }
    res1 = engine.handle(cmd)
    assert res1.message != "duplicate"
    assert res1.success is True

    res2 = engine.handle(cmd)
    assert res2.message == "duplicate"
    assert res2.success is True

def test_phase4_exit_criterion_3_cross_channel_approvals(db_conn):
    svc = ApprovalService(db_conn)
    req_id = svc.submit_request({"action": "deploy", "channel": "telegram"})
    req = svc.get_request(req_id)
    assert req.status == ApprovalStatus.PENDING

    svc.approve(req_id)
    req_after = svc.get_request(req_id)
    assert req_after.status == ApprovalStatus.APPROVED

def test_phase4_exit_criterion_4_shared_budget_engine():
    policy = BudgetPolicy(max_total=100, per_channel={"telegram": 50})
    engine = BudgetEngine(policy)

    alloc = engine.reserve_budget("telegram", 30)
    engine.commit_budget(alloc)
    assert alloc._committed is True

def test_phase4_exit_criterion_5_async_job_dispatcher():
    dispatcher = JobDispatcher()
    spec = JobSpec(job_id="job-acc-1", func=lambda x: x * 3, args=(10,))
    dispatcher.dispatch(spec)

    import time
    time.sleep(0.1)
    res = dispatcher.get_result("job-acc-1")
    assert res is not None
    assert res.status == JobStatus.SUCCESS
    assert res.result == 30

def test_phase4_exit_criterion_6_restart_recovery(db_conn):
    repo = WorkflowRepository(db_conn)
    engine = WorkflowEngine(repo)

    engine.handle({
        "command_id": "cmd-rec-1",
        "workflow_id": "wf-rec-1",
        "type": "start",
        "args": {"definition_name": "product_to_video"}
    })

    recovery_svc = WorkflowRecoveryService(db_conn)
    recovered = recovery_svc.recover_pending_workflows()
    assert "wf-rec-1" in recovered
