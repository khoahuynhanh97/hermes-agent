from datetime import datetime, timezone

import pytest

from hermes_personal.contracts import (
    AgentTurnRequest,
    AttachmentRef,
    ChannelCapabilities,
    PrincipalContext,
)


def test_turn_derives_ids_without_losing_authenticated_identity():
    principal = PrincipalContext(
        actor_id="telegram:42",
        owner_user_id="user:42",
        channel="telegram",
        session_id="telegram:100",
        roles=("admin",),
    )
    request = AgentTurnRequest(
        principal=principal,
        message="research this product",
        locale="vi-VN",
        channel_capabilities=ChannelCapabilities(
            streaming=True,
            interactive_controls=True,
            attachments=True,
        ),
    )

    assert request.channel == "telegram"
    assert request.session_id == "telegram:100"
    assert request.turn_id.startswith("turn_")
    assert request.idempotency_key == request.turn_id
    assert request.occurred_at.tzinfo is timezone.utc


def test_turn_carries_typed_attachment_and_explicit_workflow_handoff():
    principal = PrincipalContext("cli:nina", "user:42", "cli", "cli:work", ())
    attachment = AttachmentRef(
        attachment_id="asset_1",
        kind="document",
        media_type="application/pdf",
        uri="hermes://assets/asset_1",
        size_bytes=512,
        digest_sha256="a" * 64,
    )
    request = AgentTurnRequest(
        principal=principal,
        message="continue this workflow",
        workflow_id="wf_123",
        attachments=(attachment,),
        occurred_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    assert request.attachments == (attachment,)
    assert request.workflow_id == "wf_123"


def test_turn_rejects_blank_message_without_attachments():
    principal = PrincipalContext("web:42", "user:42", "web", "web:s1", ())
    with pytest.raises(ValueError, match="message or attachment"):
        AgentTurnRequest(principal=principal, message="   ")
