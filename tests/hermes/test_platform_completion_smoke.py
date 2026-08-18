"""Minimal Verification and Smoke Test for Hermes Platform Completion."""
from __future__ import annotations

import pytest
from hermes.application.product_resource_service import ProductResourceService
from hermes.security.ingress import principal_scope, build_local_cli_principal
from hermes.security.principal import current_principal
from hermes.channels.api.routes.product_research import get_product_detail
from hermes.channels.api.routes.assets import list_assets


def test_resource_pack_digest_covers_production_relevant_manifest():
    service = ProductResourceService()
    base_payload = {
        "resource_pack_id": "pack_001",
        "resource_pack_version": 1,
        "snapshot_id": "snap_001",
        "canonical_product_id": "prod_001",
        "variant_id": "var_001",
        "claims": [{"claim": "40-hour battery", "status": "verified"}],
        "identity_constraints": {"color": "black", "shape": "earbuds"},
        "assets": [{"asset_id": "asset_001", "physical_hash_filename": "hash.jpg"}],
        "lock_id": "lock_ignored",
        "created_at": "2026-08-14T00:00:00Z",
        "status": "locked",
    }

    digest = service.compute_manifest_digest(base_payload)
    assert digest == service.compute_manifest_digest({**base_payload, "lock_id": "lock_other", "created_at": "later"})
    assert digest != service.compute_manifest_digest({**base_payload, "canonical_product_id": "prod_002"})
    assert digest != service.compute_manifest_digest({**base_payload, "variant_id": "var_002"})
    assert digest != service.compute_manifest_digest({**base_payload, "claims": [{"claim": "IPX4 water resistant", "status": "verified"}]})


def test_pi_lock_digest_verification_and_binding():
    service = ProductResourceService()
    pi_lock_payload = {
        "status": "locked",
        "lock_id": "lock_pack_001",
        "resource_pack_id": "pack_001",
        "snapshot_id": "snap_001",
        "canonical_product_id": "prod_001",
        "owner_user_id": "user",
        "version": 1,
        "created_at": "2026-08-14T00:00:00Z",
        "assets": [
            {
                "asset_id": "asset_pack_001_01",
                "physical_hash_filename": "sha256_pack_001_01.jpg",
                "local_path": "/data/media/pack_001_01.jpg",
                "media_role": "original",
                "source_url": "https://example.com/product/image1.jpg",
                "source_domain": "example.com",
                "canonical_product_id": "prod_001",
                "variant_id": "var_001",
                "snapshot_id": "snap_001",
                "match_confidence": 0.98,
                "mime_type": "image/jpeg",
                "width": 1024,
                "height": 1024,
            }
        ],
    }
    pi_lock_payload["manifest_digest"] = service.compute_manifest_digest(pi_lock_payload)

    # Verify digest and bind
    binding = service.verify_and_bind("proj_001", pi_lock_payload)
    assert binding.project_id == "proj_001"
    assert binding.resource_pack_id == "pack_001"
    assert binding.manifest_digest == pi_lock_payload["manifest_digest"]

    # Convert to ProductionResourceSet for Video Factory
    prs = service.to_production_resource_set(binding, pi_lock_payload, "user")
    assert prs.id == "prs_proj_001"
    assert prs.primary_product_asset_id == "asset_pack_001_01"


def test_pi_lock_tampered_digest_fails():
    service = ProductResourceService()
    pi_lock_payload = {
        "status": "locked",
        "lock_id": "lock_pack_001",
        "resource_pack_id": "pack_001",
        "manifest_digest": "sha256:invalid_digest_hash",
        "assets": [],
    }
    with pytest.raises(ValueError, match="Manifest digest mismatch"):
        service.verify_and_bind("proj_001", pi_lock_payload)


def test_principal_scope_cleanup():
    assert current_principal.get() is None
    princ = build_local_cli_principal("session_test")
    with principal_scope(princ):
        assert current_principal.get() is princ
    assert current_principal.get() is None


def test_studio_api_projection_smoke():
    from fastapi import HTTPException

    with pytest.raises(HTTPException, match="404"):
        get_product_detail("snap_demo_001")

    assets = list_assets(role="original")
    assert assets["status"] == "ok"
    assert "assets" in assets


def test_asset_path_containment_and_owner_rejection():
    from fastapi import HTTPException
    from hermes.channels.api.routes.assets import open_asset_file, _validate_contained_media_path

    # Path traversal rejection for sensitive/outside files
    with pytest.raises(HTTPException) as exc_info:
        _validate_contained_media_path("D:/work/hermes-agent/.env")
    assert exc_info.value.status_code == 403

    # Asset lookup is owner-scoped and missing assets do not accept client paths.
    from hermes.security.principal import PrincipalContext
    princ = PrincipalContext("other_user", "other_user", "api_server", "s1")
    with principal_scope(princ):
        result = open_asset_file("asset_orig_01")
        assert result["status"] == "missing"


def test_durable_job_result_projector_and_replay(tmp_path):
    from hermes.db import Database
    from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
    from hermes.application.job_result_projector import JobResultProjector

    db = Database(tmp_path / "test.sqlite")
    repo = SQLiteGeneratedAssetRepository(db)
    projector = JobResultProjector(repo)

    payload = {"project_id": "p1", "scene_id": "s1", "resource_lock_id": "l1"}
    result = {"provider": "fake_provider", "output_path": "D:/work/hermes-agent-data/workspaces/video/videos/out.mp4"}

    # First projection
    res1 = projector.project_terminal_result("job_001", "video_generate", result, payload)
    assert res1["durable_asset_id"] == "gen_job_001"

    asset = repo.get_by_job_id("job_001")
    assert asset is not None
    assert asset["asset_id"] == "gen_job_001"
    assert asset["job_id"] == "job_001"

    # Replay same job_id -> idempotent, no duplicate
    res2 = projector.project_terminal_result("job_001", "video_generate", result, payload)
    assert res2["durable_asset_id"] == "gen_job_001"
    assert repo.count_by_job_id("job_001") == 1

    render = projector.project_terminal_result(
        "job_render_001",
        "video.render",
        {"output_path": "D:/work/hermes-agent-data/workspaces/video/videos/render.mp4"},
        payload,
    )
    assert render["timeline_render_status"] == "completed"

    export = projector.project_terminal_result(
        "job_export_001",
        "export",
        {"output_path": "D:/work/hermes-agent-data/workspaces/video/videos/final.mp4"},
        payload,
    )
    assert export["project_export_status"] == "completed"


def test_asset_projection_service_reads_pi_lock_and_generated_repository(tmp_path):
    import json
    from hermes.application.asset_projection_service import AssetProjectionService
    from hermes.db import Database
    from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository

    pi_root = tmp_path / "ProductIntelligenceData"
    image_path = pi_root / "ProductIntelligence" / "product_scout" / "images" / "abc.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"jpg")
    lock_dir = pi_root / "ProductResearch" / "baseus-bowie-ma10" / "machine"
    lock_dir.mkdir(parents=True)
    lock_payload = {
        "status": "locked",
        "lock_id": "lock_acceptance_001",
        "resource_pack_id": "pack_acceptance_001",
        "resource_pack_version": 1,
        "snapshot_id": "snap_acceptance_001",
        "canonical_product_id": "baseus-bowie-ma10",
        "variant_id": "black",
        "owner_user_id": "user",
        "product_name": "Baseus Bowie MA10",
        "brand": "Baseus",
        "claims": [],
        "identity_constraints": {"product": "Baseus Bowie MA10"},
        "assets": [
            {
                "asset_id": "orig_abc",
                "physical_hash_filename": "abc.jpg",
                "local_path": str(image_path),
                "media_role": "original",
                "source_domain": "example.com",
                "match_confidence": 0.99,
            }
        ],
    }
    lock_payload["manifest_digest"] = ProductResourceService().compute_manifest_digest(lock_payload)
    (lock_dir / "resource-pack-lock.json").write_text(json.dumps(lock_payload), encoding="utf-8")

    db = Database(tmp_path / "generated.sqlite")
    generated_repo = SQLiteGeneratedAssetRepository(db)
    generated_repo.save_asset({
        "asset_id": "gen_001",
        "project_id": "proj_001",
        "scene_id": "scene_001",
        "job_id": "job_001",
        "provider": "local",
        "resource_lock_id": "lock_acceptance_001",
        "reference_asset_ids": ["orig_abc"],
        "physical_hash_filename": "generated.mp4",
        "output_path": str(tmp_path / "generated.mp4"),
    })

    service = AssetProjectionService(pi_data_root=pi_root, generated_asset_repository=generated_repo)
    products = service.list_products("user")
    assets = service.list_assets("user")

    assert products[0]["product_name"] == "Baseus Bowie MA10"
    assert {asset["role"] for asset in assets} == {"original", "generated"}
    assert service.get_asset("user", "orig_abc")["status"] == "available"
    assert service.get_asset("user", "gen_001")["status"] == "missing"


def test_persisted_binding_and_explicit_rebinding(tmp_path):
    from hermes.db import Database
    from hermes.adapters.sqlite.product_resource_binding_repository import SQLiteProjectResourceBindingRepository

    db = Database(tmp_path / "test_bind.sqlite")
    repo = SQLiteProjectResourceBindingRepository(db)
    service = ProductResourceService(repo)

    pi_lock = {
        "status": "locked",
        "lock_id": "lock_pack_001",
        "resource_pack_id": "pack_001",
        "assets": [],
    }
    pi_lock["manifest_digest"] = service.compute_manifest_digest(pi_lock)

    # Initial binding succeeds
    binding1 = service.verify_and_bind("proj_test", pi_lock, "user")
    assert binding1.project_id == "proj_test"

    # Silent duplicate binding fails
    with pytest.raises(ValueError, match="PROJECT_BINDING_ALREADY_EXISTS"):
        service.verify_and_bind("proj_test", pi_lock, "user")

    # Explicit rebinding succeeds
    binding2 = service.rebind_project_resource("proj_test", pi_lock, "user")
    assert binding2.project_id == "proj_test"


def test_resource_pack_lock_idempotency_identity(tmp_path):
    from hermes.db import Database
    from hermes.adapters.sqlite.product_resource_binding_repository import SQLiteProjectResourceBindingRepository

    service = ProductResourceService(SQLiteProjectResourceBindingRepository(Database(tmp_path / "locks.sqlite")))
    payload = {
        "resource_pack_id": "pack_identity",
        "resource_pack_version": 1,
        "snapshot_id": "snap_1",
        "canonical_product_id": "prod_1",
        "variant_id": "var_1",
        "claims": [{"claim": "verified claim", "status": "verified"}],
        "identity_constraints": {},
        "assets": [],
    }

    lock1 = service.lock_resource_pack(payload, "user")
    lock2 = service.lock_resource_pack({**payload, "created_at": "ignored"}, "user")
    lock3 = service.lock_resource_pack({**payload, "claims": [{"claim": "changed", "status": "verified"}]}, "user")

    assert lock1["lock_id"] == lock2["lock_id"]
    assert lock1["lock_id"] != lock3["lock_id"]
