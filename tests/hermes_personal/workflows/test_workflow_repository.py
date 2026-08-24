import json
import pytest

from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.repository import DuplicateCommandError, VersionConflict, WorkflowRepository


def test_commit_new_workflow():
    conn = connect(":memory:")
    repo = WorkflowRepository(conn)
    events = [{
        "event_id": "e1",
        "command_id": "c1",
        "event_type": "test",
        "timestamp": "2026-01-01T00:00:00Z",
        "payload": {"a": 1},
    }]
    result = repo.commit_workflow(
        workflow_id="wf1",
        aggregate_json=json.dumps({"state": "init"}),
        events=events,
        outbox_message="outbox msg",
        expected_version=0,
    )
    assert result.workflow_id == "wf1"
    assert result.new_version == 1
    cur = conn.cursor()
    cur.execute("SELECT version FROM workflow WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["version"] == 1
    cur.execute("SELECT COUNT(*) as cnt FROM workflow_event WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["cnt"] == 1
    cur.execute("SELECT COUNT(*) as cnt FROM processed_command WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["cnt"] == 1
    cur.execute("SELECT COUNT(*) as cnt FROM workflow_outbox WHERE workflow_id=?", ("wf1",))
    assert cur.fetchone()["cnt"] == 1


def test_version_conflict():
    conn = connect(":memory:")
    repo = WorkflowRepository(conn)
    events = [{"event_id": "e1", "command_id": "c1"}]
    repo.commit_workflow("wf2", json.dumps({}), events, expected_version=0)
    with pytest.raises(VersionConflict):
        repo.commit_workflow("wf2", json.dumps({}), events, expected_version=0)


def test_duplicate_command_error():
    conn = connect(":memory:")
    repo = WorkflowRepository(conn)
    events1 = [{"event_id": "e1", "command_id": "c1"}]
    repo.commit_workflow("wf3", json.dumps({}), events1, expected_version=0)
    events2 = [{"event_id": "e2", "command_id": "c1"}]  # same command_id
    with pytest.raises(DuplicateCommandError):
        repo.commit_workflow("wf3", json.dumps({}), events2, expected_version=1)
