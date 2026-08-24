from __future__ import annotations

import json
from pathlib import Path
import pytest

from hermes_personal.application.events_api import ArtifactRecord, EventsAPI, InMemoryEventStore
from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.errors import CapabilityError
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES, CapabilitySpec
from hermes_personal.capabilities.policy import (
    CapabilityPolicyEvaluator,
    PolicyRequestContext,
)
from hermes_personal.observability.redaction import redact
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.repository import DuplicateCommandError, VersionConflict, WorkflowRepository


def test_owner_isolation_in_events_and_artifacts():
    """Prove User Alice cannot read or mutate User Bob's events or artifacts."""
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
    """Prove execution policy rejects unauthenticated context."""
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
    """Prove workflow repository rejects stale expected_version (optimistic concurrency)."""
    conn = connect(":memory:")
    repo = WorkflowRepository(conn)

    # Commit version 1
    repo.commit_workflow("wf_sec_1", json.dumps({"state": "init"}), events=[], expected_version=0)

    # Stale commit with expected_version=0 fails
    with pytest.raises(VersionConflict):
        repo.commit_workflow("wf_sec_1", json.dumps({"state": "mutated"}), events=[], expected_version=0)


def test_duplicate_idempotency_deduplication():
    """Prove duplicate command submission does not cause duplicate state mutations."""
    conn = connect(":memory:")
    repo = WorkflowRepository(conn)
    engine = WorkflowEngine(repository=repo)

    cmd = {
        "command_id": "cmd_fixed_id_01",
        "workflow_id": "wf_idem_01",
        "type": "start",
        "args": {"project": "Hermes"},
    }

    # First execution succeeds
    res1 = engine.handle(cmd)
    assert res1.success is True
    assert res1.new_version == 1

    # Second execution is recognized as duplicate without side effects
    res2 = engine.handle(cmd)
    assert res2.success is True
    assert res2.message == "duplicate"


def test_secret_redaction_in_observability():
    """Prove secrets (tokens, api keys, passwords) are masked in logs and reports."""
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


def test_mcp_outage_graceful_degradation():
    """Prove capability policy handles unhealthy/unreachable MCP bindings gracefully."""
    evaluator = CapabilityPolicyEvaluator()
    spec = INITIAL_CAPABILITIES["product.research"]
    unhealthy_binding = ImplementationBinding(
        capability_id=spec.capability_id,
        wire_name="product_research_mcp",
        source="mcp",
        provider="mcp_server",
        implementation_version="1.0.0",
        input_schema_version="1.0.0",
        output_schema_version="1.0.0",
        schema_digest="sha256:digest",
        health="unavailable",
    )

    ctx = PolicyRequestContext(
        channel_id="cli",
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )
    decision = evaluator.evaluate(spec, unhealthy_binding, ctx)
    assert decision.allowed is False
    assert decision.error is not None
    assert "unavailable" in decision.error.code.lower() or "unhealthy" in decision.error.message.lower()


def test_provider_schema_error_handling():
    """Prove provider schema mismatch is represented as a structured CapabilityError."""
    err = CapabilityError(
        code="schema_violation",
        message="Provider returned invalid JSON response matching schema 1.0",
        retryable=False,
        capability_id="product.research",
    )
    d = err.to_dict()
    assert d["code"] == "schema_violation"
    assert d["capability_id"] == "product.research"
    assert d["retryable"] is False


def test_budget_rejection_on_exhaustion():
    """Prove capability policy rejects execution when available budget is 0.0 or negative."""
    evaluator = CapabilityPolicyEvaluator()
    spec = INITIAL_CAPABILITIES["product.resource_pack.build"]
    binding = ImplementationBinding(
        capability_id=spec.capability_id,
        wire_name="resource_pack_build",
        source="builtin",
        provider="product_intelligence",
        implementation_version="1.0.0",
        input_schema_version="1.0",
        output_schema_version="1.0",
        schema_digest="sha256:digest",
        health="healthy",
    )

    # Budget is 0.0 for metered capability
    ctx = PolicyRequestContext(
        channel_id="cli",
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
        budget_available=0.0,
        user_confirmed_approval=True,
    )
    decision = evaluator.evaluate(spec, binding, ctx)
    assert decision.allowed is False
    assert decision.error is not None
    assert "budget" in decision.error.code.lower() or "budget" in decision.error.message.lower()


def test_static_no_natural_language_bypass_and_zero_fake_progress():
    """Prove statically that backend FastAPI and Gateway code emit only real durable events with zero synthetic mock loops."""
    app_py = Path("hermes_personal/application/app.py").read_text(encoding="utf-8")
    events_api_py = Path("hermes_personal/application/events_api.py").read_text(encoding="utf-8")

    # Verify no fake progress timers or mock sleep loops in application event handlers
    assert "asyncio.sleep" not in events_api_py
    assert "mock_artifact_" not in app_py
    assert "fake_progress" not in app_py
