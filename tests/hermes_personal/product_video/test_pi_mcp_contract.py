from __future__ import annotations

import json
from typing import Any

import pytest

from hermes_personal.product_video.handlers import (
    JobContext,
    JobFailed,
    JobSucceeded,
    MCPProductIntelligenceAdapter,
    ProductVideoJobHandlers,
    ProductVideoWorkflowState,
    TerminalJobError,
)
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.repository import WorkflowRepository


class StrictPIMCPToolRegistry:
    """Strict mock registry simulating the exact signatures and schemas of the located
    product_scout/mcp_server.py tools, rejecting unsupported keywords or invalid types.
    """

    def __init__(self) -> None:
        self.dispatched_calls: list[tuple[str, dict[str, Any]]] = []
        self.research_store: dict[str, dict[str, Any]] = {}
        self.pack_store: dict[str, dict[str, Any]] = {}
        self.lock_store: dict[str, dict[str, Any]] = {}

    def get_all_tool_names(self) -> set[str]:
        return {
            "mcp__product_intelligence__research_product",
            "mcp__product_intelligence__build_resource_pack",
            "mcp__product_intelligence__lock_resource_pack",
        }

    def dispatch(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.dispatched_calls.append((tool_name, payload))

        if tool_name == "mcp__product_intelligence__research_product":
            # Strict signature check: must NOT receive unsupported 'keywords' or 'pdp_url' keys
            forbidden_keys = {"keywords", "pdp_url", "research_result", "pack_dict"}
            unexpected = forbidden_keys.intersection(payload.keys())
            if unexpected:
                raise TypeError(f"research_product received unexpected arguments: {unexpected}")

            p_name = payload.get("product_name") or "Unknown"
            snap_id = f"snap_{len(self.research_store) + 1:03d}"
            res = {
                "status": "success",
                "error": None,
                "research_id": f"res_{snap_id}",
                "snapshot_id": snap_id,
                "persistence_status": "persisted",
                "source_summary": {"attempted": 2, "usable": 2, "challenged": 0, "blocked": 0, "failed": 0},
                "canonical_products": [
                    {
                        "canonical_product_id": f"prod_{snap_id}",
                        "name": p_name,
                        "brand": "Acme",
                        "model": "Model-X",
                        "variants": [],
                        "listings": [{"listing_id": "list_01", "host": "example.com", "seller": "AcmeStore", "price": 99.99, "currency": "USD", "availability": "in_stock"}],
                    }
                ],
                "media_assets": [
                    {
                        "asset_id": f"asset_{snap_id}_01",
                        "local_path": f"/data/media/{snap_id}_01.jpg",
                        "match_status": "matched",
                        "product_match_score": 0.95,
                        "usage_policy": "approved",
                    }
                ],
                "summary": {"usable_sources": 2, "total_assets": 1},
                "report": {"product_name": p_name, "query": payload.get("query"), "url": payload.get("url")},
            }
            self.research_store[snap_id] = res
            return res

        elif tool_name == "mcp__product_intelligence__build_resource_pack":
            # Strict signature check: must receive 'snapshot_id', and optionally 'variant_id'
            forbidden_keys = {"research_result", "pack_dict", "product_name", "keywords", "url"}
            unexpected = forbidden_keys.intersection(payload.keys())
            if unexpected:
                raise TypeError(f"build_resource_pack received unexpected arguments: {unexpected}")

            snap_id = payload.get("snapshot_id")
            if not snap_id:
                raise ValueError("snapshot_id is required")

            if snap_id not in self.research_store:
                return {"status": "not_found", "snapshot_id": snap_id}

            pack_id = f"rp_{snap_id}"
            pack_res = {
                "status": "built",
                "resource_pack_id": pack_id,
                "pack_status": "ready_to_lock",
                "reason": None,
                "canonical_product_id": f"prod_{snap_id}",
                "variant_id": payload.get("variant_id"),
                "media_count": 1,
                "claims": [{"text": "High quality product", "status": "verified"}],
                "restrictions": [],
                "completeness": {"has_images": True, "has_specs": True},
                "assets_mapping": {f"asset_{snap_id}_01": f"/data/media/{snap_id}_01.jpg"},
                "scene_plan": ["intro", "features", "outro"],
            }
            self.pack_store[pack_id] = pack_res
            return pack_res

        elif tool_name == "mcp__product_intelligence__lock_resource_pack":
            # Strict signature check: must receive 'resource_pack_id', and optionally 'owner_user_id'
            forbidden_keys = {"pack_dict", "research_result", "snapshot_id"}
            unexpected = forbidden_keys.intersection(payload.keys())
            if unexpected:
                raise TypeError(f"lock_resource_pack received unexpected arguments: {unexpected}")

            pack_id = payload.get("resource_pack_id")
            owner_user_id = payload.get("owner_user_id", "system")

            if not pack_id or pack_id not in self.pack_store:
                return {"status": "not_found", "resource_pack_id": pack_id}

            lock_id = f"lock_{pack_id}"
            lock_res = {
                "status": "locked",
                "lock_id": lock_id,
                "resource_pack_id": pack_id,
                "snapshot_id": pack_id.removeprefix("rp_"),
                "canonical_product_id": f"prod_{pack_id.removeprefix('rp_')}",
                "owner_user_id": owner_user_id,
                "version": 1,
                "manifest_digest": f"sha256:digest_{pack_id}",
                "created_at": "2026-08-28T12:00:00Z",
                "assets": [
                    {
                        "asset_id": f"asset_{pack_id}_01",
                        "local_path": f"/data/media/{pack_id}_01.jpg",
                        "media_role": "original",
                        "source_url": "https://example.com/image.jpg",
                        "match_confidence": 0.98,
                    }
                ],
            }
            self.lock_store[lock_id] = lock_res
            return lock_res

        raise ValueError(f"Unknown tool: {tool_name}")


def test_pi_adapter_outgoing_parameter_mapping():
    """Test that MCPProductIntelligenceAdapter maps pdp_url to url, keywords to query, and avoids unexpected keys."""
    registry = StrictPIMCPToolRegistry()
    wire_tools = {
        "research": "mcp__product_intelligence__research_product",
        "build_resource_pack": "mcp__product_intelligence__build_resource_pack",
        "lock_resource_pack": "mcp__product_intelligence__lock_resource_pack",
    }
    adapter = MCPProductIntelligenceAdapter(registry, wire_tools)

    # 1. Research mapping
    research_res = adapter.research(
        product_name="Drone 4K",
        keywords=["gimbal", "camera", "drone"],
        pdp_url="https://example.com/pdp/drone-4k",
    )
    assert len(registry.dispatched_calls) == 1
    tool, payload = registry.dispatched_calls[0]
    assert tool == "mcp__product_intelligence__research_product"
    assert payload == {
        "product_name": "Drone 4K",
        "url": "https://example.com/pdp/drone-4k",
        "query": "gimbal camera drone",
    }
    assert "keywords" not in payload
    assert "pdp_url" not in payload
    assert research_res["snapshot_id"] == "snap_001"
    assert research_res["persistence_status"] == "persisted"
    assert research_res["product_name"] == "Drone 4K"
    assert research_res["pdp_url"] == "https://example.com/pdp/drone-4k"

    # 2. Build pack mapping
    pack_res = adapter.build_resource_pack(research_res, variant_id="var_v1")
    assert len(registry.dispatched_calls) == 2
    tool2, payload2 = registry.dispatched_calls[1]
    assert tool2 == "mcp__product_intelligence__build_resource_pack"
    assert payload2 == {
        "snapshot_id": "snap_001",
        "variant_id": "var_v1",
    }
    assert "research_result" not in payload2
    assert pack_res["resource_pack_id"] == "rp_snap_001"
    assert pack_res["pack_status"] == "ready_to_lock"
    assert pack_res["canonical_product_id"] == "prod_snap_001"

    # 3. Lock pack mapping
    lock_res = adapter.lock_resource_pack(pack_res, owner_user_id="user_admin")
    assert len(registry.dispatched_calls) == 3
    tool3, payload3 = registry.dispatched_calls[2]
    assert tool3 == "mcp__product_intelligence__lock_resource_pack"
    assert payload3 == {
        "resource_pack_id": "rp_snap_001",
        "owner_user_id": "user_admin",
    }
    assert "pack_dict" not in payload3
    assert lock_res["lock_id"] == "lock_rp_snap_001"
    assert lock_res["owner_user_id"] == "user_admin"
    assert lock_res["manifest_digest"] == "sha256:digest_rp_snap_001"
    assert len(lock_res["assets"]) == 1


def test_build_resource_pack_missing_snapshot_fails_closed():
    """Test that build_resource_pack fails closed without dispatching if snapshot_id is missing or non-persisted."""
    registry = StrictPIMCPToolRegistry()
    wire_tools = {
        "build_resource_pack": "mcp__product_intelligence__build_resource_pack",
    }
    adapter = MCPProductIntelligenceAdapter(registry, wire_tools)

    # Missing snapshot_id
    with pytest.raises(ValueError, match="missing or non-persisted"):
        adapter.build_resource_pack({"report": "{}"})
    assert len(registry.dispatched_calls) == 0

    # Failed persistence status
    with pytest.raises(ValueError, match="missing or non-persisted"):
        adapter.build_resource_pack({"snapshot_id": "snap_failed", "persistence_status": "failed"})
    assert len(registry.dispatched_calls) == 0


def test_build_resource_pack_snapshot_not_found_raises_terminal_error():
    """Test that provider returning not_found for snapshot raises TerminalJobError."""
    registry = StrictPIMCPToolRegistry()
    wire_tools = {
        "build_resource_pack": "mcp__product_intelligence__build_resource_pack",
    }
    adapter = MCPProductIntelligenceAdapter(registry, wire_tools)

    with pytest.raises(TerminalJobError) as exc_info:
        adapter.build_resource_pack({"snapshot_id": "snap_999", "persistence_status": "persisted"})
    assert exc_info.value.code == "SNAPSHOT_NOT_FOUND"


def test_lock_resource_pack_non_lockable_status_fails_closed():
    """Test that lock_resource_pack fails closed if pack_status is needs_review, incomplete, or rejected."""
    registry = StrictPIMCPToolRegistry()
    wire_tools = {
        "lock_resource_pack": "mcp__product_intelligence__lock_resource_pack",
    }
    adapter = MCPProductIntelligenceAdapter(registry, wire_tools)

    for bad_status in ("needs_review", "incomplete", "rejected", "unknown"):
        with pytest.raises(ValueError, match="non-lockable status"):
            adapter.lock_resource_pack({"resource_pack_id": "rp_001", "pack_status": bad_status})
    assert len(registry.dispatched_calls) == 0


def test_lock_resource_pack_owner_mismatch_raises_terminal_error():
    """Test that provider returning different owner_user_id raises TerminalJobError with code OWNER_MISMATCH."""
    registry = StrictPIMCPToolRegistry()
    # Seed a pack
    registry.pack_store["rp_test"] = {"resource_pack_id": "rp_test"}
    wire_tools = {
        "lock_resource_pack": "mcp__product_intelligence__lock_resource_pack",
    }
    adapter = MCPProductIntelligenceAdapter(registry, wire_tools)

    # Monkeypatch dispatch to simulate mismatched owner
    orig_dispatch = registry.dispatch

    def bad_dispatch(tool_name, payload):
        res = orig_dispatch(tool_name, payload)
        res["owner_user_id"] = "different_user_attacker"
        return res

    registry.dispatch = bad_dispatch  # type: ignore

    with pytest.raises(TerminalJobError) as exc_info:
        adapter.lock_resource_pack({"resource_pack_id": "rp_test", "pack_status": "ready_to_lock"}, owner_user_id="legit_user")
    assert exc_info.value.code == "OWNER_MISMATCH"


def test_product_video_job_handlers_roundtrip_identifiers_through_sqlite(tmp_path):
    """Test end-to-end round-trip of PI identifiers (snapshot_id, resource_pack_id, lock_id)
    through ProductVideoJobHandlers and real SQLite workflow persistence.
    """
    db_file = tmp_path / "pi_contract_roundtrip.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_engine = WorkflowEngine(repo)

    registry = StrictPIMCPToolRegistry()
    wire_tools = {
        "research": "mcp__product_intelligence__research_product",
        "build_resource_pack": "mcp__product_intelligence__build_resource_pack",
        "lock_resource_pack": "mcp__product_intelligence__lock_resource_pack",
    }
    pi_adapter = MCPProductIntelligenceAdapter(registry, wire_tools)

    from hermes_personal.integrations.video_factory.client import VideoFactoryClient

    handlers = ProductVideoJobHandlers(
        pi_client=pi_adapter,
        video_client=VideoFactoryClient(),
        workflow_repository=repo,
        provider_mode="configured",
    )

    wf_id = "wf_pi_contract_01"

    # Step 1: Initial research job
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.RESEARCHING.value}),
        events=[{"event_id": "e_init", "command_id": "c_init", "event_type": "WorkflowStarted", "timestamp": "2026-08-28T00:00:00Z", "payload": {}}],
        expected_version=0,
    )

    ctx_res = JobContext(workflow_id=wf_id, job_id="job_res_01", owner_user_id="operator_user")
    res_out = handlers.research_job(ctx_res, product_name="Wireless ANC Earbuds", keywords=["bluetooth", "anc", "audio"], pdp_url="https://example.com/pdp/earbuds")
    assert isinstance(res_out, JobSucceeded)
    research_art = res_out.artifact_ref
    assert research_art["snapshot_id"] == "snap_001"
    assert research_art["persistence_status"] == "persisted"

    # Persist research result and advance workflow to BUILDING_RESOURCE_PACK
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value, "research_result": research_art}),
        events=[{"event_id": "e_res", "command_id": "c_res", "event_type": "ResearchCompleted", "timestamp": "2026-08-28T00:01:00Z", "payload": {"artifact": research_art}}],
        expected_version=1,
    )

    # Step 2: Build resource pack job
    ctx_pack = JobContext(workflow_id=wf_id, job_id="job_pack_01", owner_user_id="operator_user")
    pack_out = handlers.resource_pack_job(ctx_pack, research_result=research_art)
    assert isinstance(pack_out, JobSucceeded)
    pack_art = pack_out.artifact_ref
    assert pack_art["resource_pack_id"] == "rp_snap_001"
    assert pack_art["snapshot_id"] == "snap_001"
    assert pack_art["canonical_product_id"] == "prod_snap_001"
    assert pack_art["pack_status"] == "ready_to_lock"

    # Persist pack result
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value, "resource_pack": pack_art}),
        events=[{"event_id": "e_pack", "command_id": "c_pack", "event_type": "ResourcePackBuilt", "timestamp": "2026-08-28T00:02:00Z", "payload": {"artifact": pack_art}}],
        expected_version=2,
    )

    # Step 3: Lock resource pack job
    ctx_lock = JobContext(workflow_id=wf_id, job_id="job_lock_01", owner_user_id="operator_user")
    lock_out = handlers.lock_job(ctx_lock, pack_dict=pack_art)
    assert isinstance(lock_out, JobSucceeded)
    lock_art = lock_out.artifact_ref
    assert lock_art["lock_id"] == "lock_rp_snap_001"
    assert lock_art["resource_pack_id"] == "rp_snap_001"
    assert lock_art["snapshot_id"] == "snap_001"
    assert lock_art["owner_user_id"] == "operator_user"
    assert lock_art["manifest_digest"] == "sha256:digest_rp_snap_001"

    # Persist locked artifact
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.CREATING_BRIEF.value, "locked_pack": lock_art}),
        events=[{"event_id": "e_lock", "command_id": "c_lock", "event_type": "ResourcePackLocked", "timestamp": "2026-08-28T00:03:00Z", "payload": {"artifact": lock_art}}],
        expected_version=3,
    )
    conn.close()

    # Step 4: Reopen SQLite connection from scratch to verify durability across restart
    conn2 = connect(db_file)
    repo2 = WorkflowRepository(conn2)
    loaded_wf, ver = repo2.get_workflow(wf_id)
    assert ver == 4
    assert loaded_wf["state"] == ProductVideoWorkflowState.CREATING_BRIEF.value
    assert loaded_wf["locked_pack"]["lock_id"] == "lock_rp_snap_001"
    assert loaded_wf["locked_pack"]["resource_pack_id"] == "rp_snap_001"
    assert loaded_wf["locked_pack"]["snapshot_id"] == "snap_001"
    assert loaded_wf["locked_pack"]["owner_user_id"] == "operator_user"
    assert loaded_wf["locked_pack"]["manifest_digest"] == "sha256:digest_rp_snap_001"
    conn2.close()


def test_handlers_missing_prerequisites_return_non_retryable_failed(tmp_path):
    """Test that handlers return non-retryable JobFailed on missing snapshot or non-lockable status."""
    db_file = tmp_path / "prereq_test.db"
    conn = connect(db_file)
    repo = WorkflowRepository(conn)
    wf_engine = WorkflowEngine(repo)

    registry = StrictPIMCPToolRegistry()
    wire_tools = {
        "research": "mcp__product_intelligence__research_product",
        "build_resource_pack": "mcp__product_intelligence__build_resource_pack",
        "lock_resource_pack": "mcp__product_intelligence__lock_resource_pack",
    }
    pi_adapter = MCPProductIntelligenceAdapter(registry, wire_tools)

    from hermes_personal.integrations.video_factory.client import VideoFactoryClient

    handlers = ProductVideoJobHandlers(
        pi_client=pi_adapter,
        video_client=VideoFactoryClient(),
        workflow_repository=repo,
        provider_mode="configured",
    )

    wf_id = "wf_prereq_01"
    repo.commit_workflow(
        workflow_id=wf_id,
        aggregate_json=json.dumps({"state": ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value}),
        events=[{"event_id": "e_init", "command_id": "c_init", "event_type": "WorkflowStarted", "timestamp": "2026-08-28T00:00:00Z", "payload": {}}],
        expected_version=0,
    )

    ctx = JobContext(workflow_id=wf_id, job_id="job_01", owner_user_id="user1")

    # 1. resource_pack_job with missing snapshot_id -> JobFailed(retryable=False)
    fail_res1 = handlers.resource_pack_job(ctx, research_result={"persistence_status": "unpersisted"})
    assert isinstance(fail_res1, JobFailed)
    assert fail_res1.retryable is False
    assert fail_res1.code == "PREREQUISITE_FAILED"

    # 2. lock_job with non-lockable status -> JobFailed(retryable=False)
    fail_res2 = handlers.lock_job(ctx, pack_dict={"resource_pack_id": "rp_123", "pack_status": "needs_review"})
    assert isinstance(fail_res2, JobFailed)
    assert fail_res2.retryable is False
    assert fail_res2.code == "NON_LOCKABLE_STATUS"

    conn.close()
