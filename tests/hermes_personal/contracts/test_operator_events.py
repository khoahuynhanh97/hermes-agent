from datetime import timezone

import pytest

from hermes_personal.contracts import (
    AgentEvent,
    OperatorCommand,
    PrincipalContext,
    to_primitive,
)


def test_operator_command_is_owner_bound_and_idempotent():
    principal = PrincipalContext("telegram:42", "user:42", "telegram", "telegram:100")
    command = OperatorCommand(
        principal=principal,
        command_type="approve",
        target_id="approval_7",
        expected_version=3,
        payload={"decision": "approved"},
    )

    assert command.command_id.startswith("cmd_")
    assert command.idempotency_key == command.command_id
    assert command.owner_user_id == "user:42"
    assert command.occurred_at.tzinfo is timezone.utc
    assert to_primitive(command)["payload"] == {"decision": "approved"}


def test_agent_event_keeps_cross_channel_correlation():
    event = AgentEvent(
        event_type="workflow_state",
        principal_id="user:42",
        session_id="web:s1",
        turn_id="turn_1",
        workflow_id="wf_1",
        job_id="job_1",
        approval_id="approval_1",
        tool_call_id="tool_1",
        sequence=4,
        data={"state": "AwaitingBriefApproval"},
    )

    assert event.event_id.startswith("evt_")
    assert event.data["state"] == "AwaitingBriefApproval"


def test_agent_event_rejects_negative_sequence():
    with pytest.raises(ValueError, match="sequence"):
        AgentEvent(
            event_type="warning",
            principal_id="user:42",
            session_id="cli:s1",
            turn_id="turn_1",
            sequence=-1,
        )
