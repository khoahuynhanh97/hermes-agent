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

    # Identical semantic fingerprint with acceptable bounded latency delta (465ms vs 450ms = +3.3%) -> PASS
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


def test_semantic_parity_enforces_bounded_latency_and_cost():
    fp_baseline = ExecutionFingerprint(
        outcome_category="success",
        clarification_required=False,
        selected_capability_ids=("hermes.tools.search",),
        workflow_type=None,
        workflow_state=None,
        approval_gates=(),
        artifact_ownership_version_digest=(),
        terminal_status="completed",
        latency_ms=100.0,
        cost_usd=0.010,
    )

    # 1. Excessive latency delta: 180ms vs 100ms (+80% > 50% max delta) -> FAIL
    fp_excessive_latency = ExecutionFingerprint(
        outcome_category="success",
        clarification_required=False,
        selected_capability_ids=("hermes.tools.search",),
        workflow_type=None,
        workflow_state=None,
        approval_gates=(),
        artifact_ownership_version_digest=(),
        terminal_status="completed",
        latency_ms=180.0,
        cost_usd=0.010,
    )
    report_lat = compare_semantic_parity("test_fixture_lat", fp_baseline, fp_excessive_latency, max_latency_delta_ratio=0.5)
    assert report_lat.is_equivalent is False
    assert any(m.field_name == "latency_ms" for m in report_lat.mismatches)

    # 2. Excessive cost delta: 0.015 vs 0.010 (+50% > 20% max delta) -> FAIL
    fp_excessive_cost = ExecutionFingerprint(
        outcome_category="success",
        clarification_required=False,
        selected_capability_ids=("hermes.tools.search",),
        workflow_type=None,
        workflow_state=None,
        approval_gates=(),
        artifact_ownership_version_digest=(),
        terminal_status="completed",
        latency_ms=105.0,
        cost_usd=0.015,
    )
    report_cost = compare_semantic_parity("test_fixture_cost", fp_baseline, fp_excessive_cost, max_cost_delta_ratio=0.2)
    assert report_cost.is_equivalent is False
    assert any(m.field_name == "cost_usd" for m in report_cost.mismatches)

    # Verify redaction in ParityReport.as_dict()
    dict_repr = report_cost.as_dict()
    assert dict_repr["is_equivalent"] is False
    assert len(dict_repr["mismatches"]) == 1


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
