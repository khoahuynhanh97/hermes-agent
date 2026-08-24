import json
import uuid
from datetime import datetime
import sqlite3
import pytest

from hermes_personal.workflows.approvals import ApprovalService, ApprovalStatus, ApprovalRequest

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()

@pytest.fixture
def service(db_conn):
    return ApprovalService(db_conn)

def test_submit_and_get(service):
    payload = {"action": "deploy", "target": "prod"}
    request_id = service.submit_request(payload)
    req = service.get_request(request_id)
    assert isinstance(req, ApprovalRequest)
    assert req.request_id == request_id
    assert req.status == ApprovalStatus.PENDING
    assert req.payload == payload
    # timestamps ISO format ending with Z
    datetime.fromisoformat(req.created_at.rstrip("Z"))
    datetime.fromisoformat(req.updated_at.rstrip("Z"))

def test_approve(service):
    rid = service.submit_request({"foo": "bar"})
    service.approve(rid)
    req = service.get_request(rid)
    assert req.status == ApprovalStatus.APPROVED

def test_reject(service):
    rid = service.submit_request({"foo": "bar"})
    service.reject(rid)
    req = service.get_request(rid)
    assert req.status == ApprovalStatus.REJECTED

def test_invalid_transition(service):
    rid = service.submit_request({})
    service.approve(rid)
    with pytest.raises(ValueError):
        service.reject(rid)
    with pytest.raises(ValueError):
        service.approve(rid)

def test_missing_request(service):
    fake_id = str(uuid.uuid4())
    with pytest.raises(KeyError):
        service.get_request(fake_id)
    with pytest.raises(KeyError):
        service.approve(fake_id)
    with pytest.raises(KeyError):
        service.reject(fake_id)
