import sqlite3
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.recovery import WorkflowRecoveryService

def setup_recovery():
    conn = connect(':memory:')
    # Insert sample workflows
    conn.executescript('''
        INSERT INTO workflow (workflow_id, aggregate_json, version) VALUES ('wf1', '{}', 0);
        INSERT INTO workflow (workflow_id, aggregate_json, version) VALUES ('wf2', '{}', 0);
        INSERT INTO workflow_outbox (workflow_id, message, created_at) VALUES ('wf1', 'msg1', datetime('now'));
        INSERT INTO workflow_outbox (workflow_id, message, created_at) VALUES ('wf2', 'msg2', datetime('now'));
    ''')
    return WorkflowRecoveryService(conn), conn

def test_recover_pending_workflows():
    service, conn = setup_recovery()
    ids = service.recover_pending_workflows()
    assert set(ids) == {'wf1', 'wf2'}

def test_replay_outbox_remains_durable_until_acknowledged():
    service, conn = setup_recovery()
    msgs = service.replay_outbox()
    assert msgs == [('wf1', 'msg1'), ('wf2', 'msg2')]
    # A crash before ACK must replay the same messages.
    assert service.replay_outbox() == msgs
    service.ack_outbox('wf1', 'msg1')
    assert service.replay_outbox() == [('wf2', 'msg2')]
    service.ack_outbox('wf2', 'msg2')
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as cnt FROM workflow_outbox')
    assert cur.fetchone()['cnt'] == 0
    assert service.replay_outbox() == []


def test_recovery_delegates_to_outbox_repository_without_lease_bypass():
    from unittest.mock import MagicMock

    conn = connect(":memory:")
    service = WorkflowRecoveryService(conn)

    service.outbox_repository.enqueue("wf_del", "msg_del")
    claims = service.outbox_repository.claim("worker_del")
    assert len(claims) == 1
    c = claims[0]

    original_ack = service.outbox_repository.ack
    spy_ack = MagicMock(side_effect=original_ack)
    service.outbox_repository.ack = spy_ack

    service.ack_outbox("wf_del", "msg_del")

    from unittest.mock import ANY

    assert spy_ack.called
    kwargs = spy_ack.call_args.kwargs
    assert kwargs["outbox_id"] == c.outbox_id
    assert kwargs["lease_token"] == c.lease_token
    assert kwargs["worker_id"] == c.lease_owner

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM workflow_outbox")
    assert cur.fetchone()["cnt"] == 0
