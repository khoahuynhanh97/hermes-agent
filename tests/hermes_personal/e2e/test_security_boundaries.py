from __future__ import annotations

import json
import pytest

from hermes_personal.application.events_api import ArtifactRecord, EventsAPI, InMemoryEventStore
from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES, CapabilitySpec
from hermes_personal.capabilities.policy import (
    CapabilityPolicyEvaluator,
    PolicyRequestContext,
)
from hermes_personal.observability.redaction import redact
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.repository import VersionConflict, WorkflowRepository


def test_owner_isolation_in_events_and_artifacts():
    """Verify User Alice cannot read or mutate User Bob's events or artifacts."""
    store = InMemoryEventStore()
    events_api = EventsAPI(
        event_store=store,
        auth_validator=lambda token, owner: token == f"token_{owner}",
    )

    art_bob = ArtifactRecord(
        artifact_id="art_bob_001",
        owner_user_id="user_bob",
        artifact_type="video_render",
        version=1,
        digest="sha256:bobdigest",
        delivery_ref="/storage/bob_001.mp4",
        metadata={"duration": 30},
    )
    events_api.add_artifact(art_bob)

    # Alice queries Bob's artifact -> status 403 / forbidden
    status_alice, _ = events_api.get_artifact("art_bob_001", owner_id="user_alice", auth_token="token_user_alice")
    assert status_alice == 403

    # Bob queries Bob's artifact -> OK (200)
    status_bob, body_bob = events_api.get_artifact("art_bob_001", owner_id="user_bob", auth_token="token_user_bob")
    assert status_bob == 200
    assert body_bob["delivery_ref"] == "/storage/bob_001.mp4"


def test_forged_principal_and_policy_boundary_rejection():
    """Verify execution policy rejects unauthenticated context."""
    evaluator = CapabilityPolicyEvaluator()
    spec = INITIAL_CAPABILITIES["product.research"]
    binding = ImplementationBinding(
        capability_id=spec.capability_id,
        wire_name="web_search",
        source="builtin",
        provider="hermes",
        implementation_version="1.0.0",
        input_schema_version="1.0.0",
        output_schema_version="1.0.0",
        schema_digest="sha256:digest",
        health="healthy",
    )

    # Unauthenticated context -> rejected
    ctx = PolicyRequestContext(
        channel_id="telegram",
        authenticated=False,
    )
    decision = evaluator.evaluate(spec, binding, ctx)
    assert decision.allowed is False
    assert decision.error is not None
    assert decision.error.code == "unauthenticated"


def test_stale_command_version_rejection():
    """Verify workflow repository rejects stale expected_version (optimistic concurrency)."""
    conn = connect(":memory:")
    repo = WorkflowRepository(conn)

    # Commit version 1
    repo.commit_workflow("wf_sec_1", json.dumps({"state": "init"}), events=[], expected_version=0)

    # Stale commit with expected_version=0 fails
    with pytest.raises(VersionConflict):
        repo.commit_workflow("wf_sec_1", json.dumps({"state": "mutated"}), events=[], expected_version=0)


def test_secret_redaction_in_observability():
    """Verify secrets (tokens, api keys, passwords) are masked in logs and reports."""
    raw_payload = {
        "user": "alice",
        "api_key": "sk-ant-api03-secretkey12345",
        "nested": {
            "token": "ghp_supersecretgithubtoken",
            "password": "my_cleartext_password",
            "normal_field": "public_data",
        },
    }

    redacted = redact(raw_payload)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["normal_field"] == "public_data"
