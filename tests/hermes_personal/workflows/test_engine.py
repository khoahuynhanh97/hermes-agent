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
