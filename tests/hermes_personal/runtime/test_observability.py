from __future__ import annotations

import pytest

from hermes_personal.observability.context import CorrelationContext
from hermes_personal.observability.health import ComponentHealth, HealthReport, HealthStatus
from hermes_personal.observability.redaction import redact, REDACTED_PLACEHOLDER


def test_correlation_chain_is_preserved():
    context = CorrelationContext(
        owner_user_id="user:1",
        session_id="session:1",
        turn_id="turn:1",
        workflow_id="wf:1",
        job_id="job:1",
        approval_id="approval:1",
        tool_id="tool:1",
    )
    fields = context.as_log_fields()
    assert fields["owner_user_id"] == "user:1"
    assert fields["session_id"] == "session:1"
    assert fields["turn_id"] == "turn:1"
    assert fields["workflow_id"] == "wf:1"
    assert fields["job_id"] == "job:1"
    assert fields["approval_id"] == "approval:1"
    assert fields["tool_id"] == "tool:1"


def test_correlation_context_with_child():
    parent = CorrelationContext(
        owner_user_id="user:1",
        session_id="session:1",
        workflow_id="wf:1",
    )
    child = parent.with_child(job_id="job:42", tool_id="tool:render")
    assert child.owner_user_id == "user:1"
    assert child.session_id == "session:1"
    assert child.workflow_id == "wf:1"
    assert child.job_id == "job:42"
    assert child.tool_id == "tool:render"


@pytest.mark.parametrize("key", ["authorization", "api_key", "token", "cookie", "password", "secret", "private_key"])
def test_secret_fields_are_redacted(key):
    payload = {
        key: "super_secret_value_123",
        "workflow_id": "wf:1",
        "nested": {
            key: "nested_secret",
            "safe_field": "hello world",
        },
        "list_data": [
            {key: "in_list_secret", "name": "test"},
        ],
    }
    redacted = redact(payload)
    assert redacted[key] == REDACTED_PLACEHOLDER
    assert redacted["workflow_id"] == "wf:1"
    assert redacted["nested"][key] == REDACTED_PLACEHOLDER
    assert redacted["nested"]["safe_field"] == "hello world"
    assert redacted["list_data"][0][key] == REDACTED_PLACEHOLDER
    assert redacted["list_data"][0]["name"] == "test"


def test_redact_handles_primitive_values():
    assert redact("simple_string") == "simple_string"
    assert redact(12345) == 12345
    assert redact(None) is None
    assert redact([1, 2, "three"]) == [1, 2, "three"]


def test_required_unhealthy_dependency_blocks_readiness():
    c_gw = ComponentHealth(name="gateway", required=True, status="healthy")
    c_mcp = ComponentHealth(name="mcp", required=True, status="unavailable", details="Connection refused")
    report = HealthReport.from_components((c_gw, c_mcp))

    assert report.ready is False
    assert report.live is True


def test_optional_degraded_dependency_does_not_block_readiness():
    c_gw = ComponentHealth(name="gateway", required=True, status="healthy")
    c_opt = ComponentHealth(name="optional_analytics", required=False, status="degraded", details="High latency")
    report = HealthReport.from_components((c_gw, c_opt))

    assert report.ready is True
    assert report.live is True


def test_all_required_healthy_is_ready():
    c_gw = ComponentHealth(name="gateway", required=True, status="healthy")
    c_db = ComponentHealth(name="database", required=True, status="healthy")
    c_wf = ComponentHealth(name="workflows", required=True, status="healthy")
    report = HealthReport.from_components((c_gw, c_db, c_wf))

    assert report.ready is True
    assert report.live is True
    data = report.as_dict()
    assert data["ready"] is True
    assert len(data["components"]) == 3


def test_stopping_component_makes_liveness_false():
    c_gw = ComponentHealth(name="gateway", required=True, status="stopping")
    report = HealthReport.from_components((c_gw,))

    assert report.ready is False
    assert report.live is False
