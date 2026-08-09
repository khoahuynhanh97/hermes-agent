from __future__ import annotations

import csv

import pytest
from dataclasses import replace
from hermes.domain.affiliate_research import ContentPackage, PackageStatus

from mcp_servers.product.server import (
    product_get_run,
    product_import_candidates,
    product_list_packages,
    product_score_shortlist,
)


def _write_export(path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["item_id", "product_name", "category", "price", "sold", "product_link"],
        )
        writer.writeheader()
        writer.writerows(
            {
                "item_id": str(index),
                "product_name": f"Mouse {index}",
                "category": "mouse",
                "price": "349000",
                "sold": str(12_000 + index),
                "product_link": f"https://shopee.vn/{index}",
            }
            for index in range(15)
        )


def test_product_tools_split_import_score_and_state_reads(tmp_path, monkeypatch):
    import_root = tmp_path / "imports"
    import_root.mkdir()
    _write_export(import_root / "products.csv")
    monkeypatch.setenv("AFFILIATE_IMPORT_DIR", str(import_root))
    monkeypatch.setenv("HERMES_P1_DB_PATH", str(tmp_path / "p1.db"))

    imported = product_import_candidates(
        owner_user_id="user-42",
        csv_path="products.csv",
        run_id="p1-run-1",
    )
    repeated = product_import_candidates(
        owner_user_id="user-42",
        csv_path="products.csv",
        run_id="p1-run-1",
    )
    shortlist = product_score_shortlist(
        owner_user_id="user-42",
        run_id="p1-run-1",
        minimum=15,
        maximum=15,
    )
    run = product_get_run(owner_user_id="user-42", run_id="p1-run-1")
    packages = product_list_packages(owner_user_id="user-42", run_id="p1-run-1")

    assert imported == {
        "ok": True,
        "run_id": "p1-run-1",
        "imported": 15,
        "updated": 0,
        "rejected": 0,
        "errors": 0,
    }
    assert repeated["imported"] == 0
    assert repeated["updated"] == 15
    assert shortlist["ok"] is True
    assert shortlist["run_id"] == "p1-run-1"
    assert len(shortlist["shortlist"]) == 15
    assert run["status"] == "completed"
    assert run["counters"]["shortlisted"] == 15
    assert len(run["products"]) == 15
    assert len(run["shortlist"]) == 15
    assert packages == {"ok": True, "run_id": "p1-run-1", "packages": []}


def test_product_import_candidates_rejects_csv_outside_configured_root(tmp_path, monkeypatch):
    import_root = tmp_path / "imports"
    import_root.mkdir()
    outside_path = tmp_path / "outside.csv"
    outside_path.write_text("item_id\n1\n", encoding="utf-8")
    monkeypatch.setenv("AFFILIATE_IMPORT_DIR", str(import_root))
    monkeypatch.setenv("HERMES_P1_DB_PATH", str(tmp_path / "p1.db"))

    with pytest.raises(ValueError, match="inside AFFILIATE_IMPORT_DIR"):
        product_import_candidates(
            owner_user_id="user-42",
            csv_path=str(outside_path),
            run_id="p1-run-2",
        )


def test_product_tools_reject_missing_run_and_owner_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_P1_DB_PATH", str(tmp_path / "p1.db"))

    with pytest.raises(LookupError, match="affiliate run not found"):
        product_score_shortlist("user-42", "missing-run")

    import_root = tmp_path / "imports"
    import_root.mkdir()
    _write_export(import_root / "products.csv")
    monkeypatch.setenv("AFFILIATE_IMPORT_DIR", str(import_root))
    product_import_candidates("user-42", "products.csv", "owned-run")

    with pytest.raises(LookupError, match="affiliate run not found"):
        product_get_run("other-user", "owned-run")
    with pytest.raises(LookupError, match="affiliate run not found"):
        product_score_shortlist("other-user", "owned-run")


def _review_package(package_id="pkg-1", owner="owner-1", status=PackageStatus.PENDING_REVIEW):
    return ContentPackage(
        id=package_id,
        owner_user_id=owner,
        product_id="product-1",
        run_id="run-1",
        revision=1,
        status=status,
        audience="office workers",
        angle="desk setup",
        angle_reason="clear use case",
        hook="A useful hook",
        script="A bounded script",
        duration_seconds=30,
        storyboard=(),
        ai_prompts=(),
        voiceover_plan="voiceover",
        text_overlays=(),
        claims=(),
        warnings=(),
        asset_rights={},
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def test_product_business_approval_is_owner_scoped_and_idempotent(monkeypatch):
    import mcp_servers.product.server as product_module

    class Repository:
        def __init__(self):
            self.package = _review_package()
            self.events = []

        def get_package(self, package_id, owner_user_id):
            if package_id != self.package.id or owner_user_id != self.package.owner_user_id:
                return None
            return self.package

        def transition_package(self, package_id, owner_user_id, action, reason):
            if self.get_package(package_id, owner_user_id) is None:
                raise LookupError(package_id)
            target = {
                "approve": PackageStatus.APPROVED,
                "reject": PackageStatus.REJECTED,
                "revise": PackageStatus.REVISION_REQUESTED,
            }[action]
            if self.package.status is target:
                return self.package
            if self.package.status is not PackageStatus.PENDING_REVIEW:
                raise ValueError("invalid transition")
            self.package = replace(self.package, status=target)
            self.events.append((action, reason))
            return self.package

    repository = Repository()
    monkeypatch.setattr(product_module, "_repository", lambda: repository)
    approved = product_module.product_approve_package("owner-1", "pkg-1", "ship it")
    repeated = product_module.product_approve_package("owner-1", "pkg-1", "duplicate")

    assert approved["package"]["status"] == "approved"
    assert approved["changed"] is True
    assert repeated["changed"] is False
    assert repository.events == [("approve", "ship it")]
    with pytest.raises(ValueError, match="PACKAGE_NOT_FOUND"):
        product_module.product_reject_package("owner-2", "pkg-1")


def test_product_business_approval_rejects_invalid_transition(monkeypatch):
    import mcp_servers.product.server as product_module

    package = _review_package(status=PackageStatus.APPROVED)

    class Repository:
        def get_package(self, package_id, owner_user_id):
            return package

        def transition_package(self, package_id, owner_user_id, action, reason):
            raise ValueError("cannot reject package in approved status")

    monkeypatch.setattr(product_module, "_repository", lambda: Repository())
    with pytest.raises(ValueError, match="approved status"):
        product_module.product_reject_package("owner-1", "pkg-1")
