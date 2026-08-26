import json
import pytest
import sqlite3

from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.engine import WorkflowEngine, CommandResult
from hermes_personal.workflows.repository import WorkflowRepository
from hermes_personal.workflows.models import IllegalTransition


def setup_engine():
    conn = connect(":memory:")
    repo = WorkflowRepository(conn)
    engine = WorkflowEngine(repo)
    return engine, conn


def test_start_command_creates_workflow():
    engine, conn = setup_engine()
    cmd = {
        "command_id": "c1",
        "workflow_id": "wf1",
        "type": "start",
        "args": {},
    }
    result = engine.handle(cmd)
    assert isinstance(result, CommandResult)
    assert result.new_version == 1
    cur = conn.cursor()
    cur.execute("SELECT version FROM workflow WHERE workflow_id=?", ("wf1",))
    row = cur.fetchone()
    assert row["version"] == 1
    # state should be 'started'
    assert engine._cache["wf1"]["state"] == "started"


def test_invalid_transition_raises():
    engine, _ = setup_engine()
    # start workflow
    engine.handle({"command_id": "c1", "workflow_id": "wf1", "type": "start", "args": {}})
    # approve directly from 'started' is invalid
    with pytest.raises(IllegalTransition):
        engine.handle({"command_id": "c2", "workflow_id": "wf1", "type": "approve", "args": {}})


def test_invalid_transition_does_not_persist_anything():
    engine, conn = setup_engine()
    engine.handle({"command_id": "c1", "workflow_id": "wf1", "type": "start", "args": {}})

    with pytest.raises(IllegalTransition):
        engine.handle({"command_id": "c2", "workflow_id": "wf1", "type": "approve", "args": {}})

    cur = conn.cursor()
    cur.execute("SELECT aggregate_json, version FROM workflow WHERE workflow_id=?", ("wf1",))
    workflow = cur.fetchone()
    assert json.loads(workflow["aggregate_json"]) == {"state": "started"}
    assert workflow["version"] == 1
    cur.execute("SELECT COUNT(*) AS cnt FROM workflow_event WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["cnt"] == 1
    cur.execute("SELECT COUNT(*) AS cnt FROM processed_command WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["cnt"] == 1


def test_unknown_command_does_not_create_workflow():
    engine, conn = setup_engine()

    with pytest.raises(IllegalTransition):
        engine.handle({"command_id": "unknown-1", "workflow_id": "wf1", "type": "unknown", "args": {}})

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM workflow WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["cnt"] == 0
    cur.execute("SELECT COUNT(*) AS cnt FROM workflow_event WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["cnt"] == 0
    cur.execute("SELECT COUNT(*) AS cnt FROM processed_command WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["cnt"] == 0


def test_aggregate_persists_state_after_transition():
    engine, conn = setup_engine()
    engine.handle({"command_id": "c1", "workflow_id": "wf1", "type": "start", "args": {}})

    cur = conn.cursor()
    cur.execute("SELECT aggregate_json FROM workflow WHERE workflow_id=?", ("wf1",))
    assert json.loads(cur.fetchone()["aggregate_json"]) == {"state": "started"}


def test_fresh_engine_loads_persisted_state_and_duplicate_version():
    engine1, conn = setup_engine()
    command = {"command_id": "c1", "workflow_id": "wf1", "type": "start", "args": {}}
    assert engine1.handle(command).new_version == 1

    engine2 = WorkflowEngine(WorkflowRepository(conn))
    duplicate = engine2.handle(command)
    assert duplicate.message == "duplicate"
    assert duplicate.new_version == 1
    assert engine2.get_workflow_state("wf1") == ("started", 1)

    next_result = engine2.handle(
        {"command_id": "c2", "workflow_id": "wf1", "type": "request_approval", "args": {}}
    )
    assert next_result.new_version == 2
    assert engine2.get_workflow_state("wf1") == ("approval_requested", 2)


def test_engine_refreshes_stale_cache_before_command():
    engine1, conn = setup_engine()
    engine1.handle({"command_id": "c1", "workflow_id": "wf1", "type": "start", "args": {}})
    engine2 = WorkflowEngine(WorkflowRepository(conn))
    engine2.handle(
        {"command_id": "c2", "workflow_id": "wf1", "type": "request_approval", "args": {}}
    )

    result = engine1.handle({"command_id": "c3", "workflow_id": "wf1", "type": "approve", "args": {}})
    assert result.new_version == 3
    assert engine1.get_workflow_state("wf1") == ("approved", 3)


def test_job_succeeded_transitions_to_terminal_completed_state():
    engine, conn = setup_engine()
    engine.set_workflow_state("wf1", "job_dispatched", version=1)

    result = engine.handle({"command_id": "c1", "workflow_id": "wf1", "type": "job_succeeded", "args": {}})

    assert result.new_version == 2
    assert engine.get_workflow_state("wf1") == ("completed", 2)
    cur = conn.cursor()
    cur.execute("SELECT aggregate_json FROM workflow WHERE workflow_id=?", ("wf1",))
    assert json.loads(cur.fetchone()["aggregate_json"]) == {"state": "completed"}
    with pytest.raises(IllegalTransition):
        engine.handle({"command_id": "c2", "workflow_id": "wf1", "type": "cancel", "args": {}})


def test_set_workflow_state_does_not_swallow_persistence_error():
    conn = sqlite3.connect(":memory:")
    engine = WorkflowEngine(WorkflowRepository(conn))

    with pytest.raises(sqlite3.OperationalError):
        engine.set_workflow_state("wf1", "started")


def test_duplicate_command_returns_same_version_and_no_extra_event():
    engine, conn = setup_engine()
    cmd = {"command_id": "c1", "workflow_id": "wf1", "type": "start", "args": {}}
    first = engine.handle(cmd)
    assert first.new_version == 1
    # duplicate
    dup = engine.handle(cmd)
    assert dup.new_version == 1
    assert dup.message == "duplicate"
    # events count should stay 1
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM workflow_event WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["cnt"] == 1
