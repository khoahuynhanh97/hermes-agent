from __future__ import annotations

import pytest

from hermes_personal.cutover.inventory import (
    RouteEntry,
    RouteInventory,
    RouteInventoryError,
    get_default_production_inventory,
)
from hermes_personal.cutover.parity import (
    ExecutionFingerprint,
    OrderedCutoverCoordinator,
    compare_semantic_parity,
)


def test_default_production_route_inventory_is_valid():
    inventory = get_default_production_inventory()
    inventory.validate()
    assert len(inventory.routes) >= 6

    # Verify all natural language routes terminate at HermesTurnService
    for route in inventory.routes:
        if route.classification == "natural_language":
            assert "HermesTurnService" in route.target_service or "turn" in route.target_service.lower()


def test_route_inventory_rejects_prohibited_and_misrouted_paths():
    # 1. Prohibited direct provider path
    inv = RouteInventory()
    inv.register_route(RouteEntry(
        path="/api/chat/openai_direct",
        method="POST",
        channel="web",
        classification="prohibited_direct_provider",
        target_service="OpenAIClient",
    ))
    with pytest.raises(RouteInventoryError, match="Prohibited direct provider route detected"):
        inv.validate()

    # 2. Natural language route bypassing HermesTurnService
    inv2 = RouteInventory()
    inv2.register_route(RouteEntry(
        path="/api/bypass_turn",
        method="POST",
        channel="telegram",
        classification="natural_language",
        target_service="RawLLMBridge",
    ))
    with pytest.raises(RouteInventoryError, match="must terminate at HermesTurnService"):
        inv2.validate()


def test_semantic_parity_comparison():
    fp_baseline = ExecutionFingerprint(
        outcome_category="workflow_started",
        clarification_required=False,
        selected_capability_ids=("hermes.tools.web_search", "hermes.tools.media_render"),
        workflow_type="product_video_pipeline",
        workflow_state="awaiting_approval",
        approval_gates=("creative_brief_review",),
        artifact_ownership_version_digest=(("user_alice", 1, "sha256:abc123digest"),),
        terminal_status="pending_operator",
        latency_ms=450.0,
        cost_usd=0.012,
    )

    # Identical semantic fingerprint with slight latency delta -> PASS
    fp_candidate = ExecutionFingerprint(
        outcome_category="workflow_started",
        clarification_required=False,
        selected_capability_ids=("hermes.tools.media_render", "hermes.tools.web_search"),  # order differs, set equal
        workflow_type="product_video_pipeline",
        workflow_state="awaiting_approval",
        approval_gates=("creative_brief_review",),
        artifact_ownership_version_digest=(("user_alice", 1, "sha256:abc123digest"),),
        terminal_status="pending_operator",
        latency_ms=465.0,
        cost_usd=0.012,
    )

    report = compare_semantic_parity("test_fixture_001", fp_baseline, fp_candidate)
    assert report.is_equivalent is True
    assert len(report.mismatches) == 0

    # Semantic mismatch: capability omitted -> FAIL
    fp_mismatch = ExecutionFingerprint(
        outcome_category="workflow_started",
        clarification_required=False,
        selected_capability_ids=("hermes.tools.web_search",),  # missing media_render
        workflow_type="product_video_pipeline",
        workflow_state="awaiting_approval",
        approval_gates=("creative_brief_review",),
        artifact_ownership_version_digest=(("user_alice", 1, "sha256:abc123digest"),),
        terminal_status="pending_operator",
        latency_ms=450.0,
        cost_usd=0.012,
    )

    report2 = compare_semantic_parity("test_fixture_002", fp_baseline, fp_mismatch)
    assert report2.is_equivalent is False
    assert any(m.field_name == "selected_capability_ids" for m in report2.mismatches)


def test_ordered_reversible_cutover_progression():
    coord = OrderedCutoverCoordinator()

    # Stage 0: CLI & Omni
    cli_state = coord.get_state("cli")
    omni_state = coord.get_state("omni")
    cli_state.contract_suite_passed = True
    cli_state.rollback_tested = True
    omni_state.contract_suite_passed = True
    omni_state.rollback_tested = True

    # Cutover Stage 0
    assert coord.cutover_stage(0) is True
    assert coord.get_state("cli").cutover_enabled is True
    assert coord.get_state("omni").cutover_enabled is True

    # Stage 1: Telegram
    tel_state = coord.get_state("telegram")
    tel_state.contract_suite_passed = True
    tel_state.rollback_tested = True
    assert coord.cutover_stage(1) is True
    assert coord.get_state("telegram").cutover_enabled is True

    # Rollback Telegram on threshold violation
    coord.rollback_channel("telegram")
    assert coord.get_state("telegram").cutover_enabled is False
    # CLI and Omni remain enabled
    assert coord.get_state("cli").cutover_enabled is True
    assert coord.get_state("omni").cutover_enabled is True
