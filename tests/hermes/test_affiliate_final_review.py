from __future__ import annotations

import pytest

from hermes.db import Database
from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ContentPackage,
    PackageStatus,
)


def _product(product_id: str, external_id: str) -> AffiliateProduct:
    return AffiliateProduct(
        id=product_id,
        owner_user_id="42",
        platform="shopee",
        external_product_id=external_id,
        name=f"Product {external_id}",
        category="mouse",
        price_vnd=300_000,
        sold_count=100,
        rating=4.8,
        review_count=20,
        commission_rate=0.1,
        shop_name="Shop",
        product_url=f"https://example.test/{external_id}",
        image_urls=(f"https://example.test/{external_id}.jpg",),
        visual_signals=("movement",),
        source_type="affiliate_csv",
        source_url="https://example.test/feed.csv",
        authorization_scope="user_export",
        rights_status="affiliate_reference",
        content_hash=f"hash-{external_id}",
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )


def test_v4_migration_creates_run_catalog_outbox_and_provenance(tmp_path):
    database = Database(tmp_path / "hermes.db")
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        reference_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(affiliate_references)")
        }

    assert {
        "affiliate_run_products",
        "affiliate_projection_outbox",
        "affiliate_research_briefs",
    } <= tables
    assert {"source_type", "content_hash"} <= reference_columns


def test_run_catalog_and_projection_outbox_are_durable(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    repository.create_run("run-1", "42", "key-1")
    first = repository.upsert_product(_product("p1", "1"))
    second = repository.upsert_product(_product("p2", "2"))
    repository.record_run_product("run-1", first.id)
    assert repository.list_products("42", "run-1") == [first]

    repository.complete_run(
        "run-1",
        {"imported": 1, "updated": 0, "rejected": 2, "errors": 3},
        ("sheets", "telegram"),
    )
    fresh = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))

    assert [item["projection"] for item in fresh.pending_projections("run-1")] == [
        "sheets",
        "telegram",
    ]
    assert fresh.create_run("run-1", "42", "key-1")["counters"]["errors"] == 3
    assert second not in fresh.list_products("42", "run-1")


def test_run_completion_rolls_back_when_outbox_creation_fails(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    repository.create_run("run-1", "42", "key-1")

    with pytest.raises(ValueError, match="projection"):
        repository.complete_run("run-1", {"imported": 1}, ("sheets", ""))

    run = repository.create_run("run-1", "42", "key-1")
    assert run["status"] == "running"
    assert repository.pending_projections("run-1") == []


def test_revision_transaction_rolls_back_child_parent_and_event_on_fault(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )

    database = Database(tmp_path / "hermes.db")
    repository = SQLiteAffiliateResearchRepository(database)
    repository.create_run("run-1", "42", "key-1")
    repository.upsert_product(_product("p1", "1"))
    parent = ContentPackage(
        id="pkg-1",
        owner_user_id="42",
        product_id="p1",
        run_id="run-1",
        revision=1,
        status=PackageStatus.PENDING_REVIEW,
        audience="office_worker",
        angle="Angle",
        angle_reason="Reason",
        hook="Original hook",
        script="Original script",
        duration_seconds=45,
        storyboard=(),
        ai_prompts=(),
        voiceover_plan="Voice",
        text_overlays=(),
        claims=(),
        warnings=(),
        asset_rights={},
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )
    repository.save_package(parent)
    revision = ContentPackage(
        **{
            **parent.__dict__,
            "id": "pkg-1:r2",
            "revision": 2,
            "hook": "Revised hook",
        }
    )
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_revision_event
            BEFORE INSERT ON affiliate_approval_events
            BEGIN
                SELECT RAISE(ABORT, 'injected event failure');
            END
            """
        )

    with pytest.raises(Exception, match="injected event failure"):
        repository.save_revision("pkg-1", "42", revision, "feedback")

    assert repository.get_package("pkg-1:r2", "42") is None
    assert repository.get_package("pkg-1", "42").status is PackageStatus.PENDING_REVIEW


def test_tiktok_collector_persists_owner_scoped_deterministic_metadata(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )
    from hermes.application.affiliate_reference_service import TikTokReferenceCollector
    from hermes.domain.affiliate_research import ReferenceMetadata

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    products = [
        repository.upsert_product(_product("p1", "1")),
        repository.upsert_product(_product("p2", "2")),
    ]
    calls = []

    class Adapter:
        def fetch(self, url, owner_user_id, product_id):
            calls.append((url, owner_user_id, product_id))
            return ReferenceMetadata(
                id=f"ref-{product_id}",
                owner_user_id=owner_user_id,
                product_id=product_id,
                platform="tiktok",
                source_url=url,
                title="Pattern",
                author_name="Creator",
                author_url="",
                thumbnail_url="",
                caption="Pattern",
                embed_html="",
                authorization_scope="public_oembed",
                rights_status="reference_only",
                media_local_path="",
                collected_at="2026-08-01T00:00:00+00:00",
                source_type="tiktok_oembed",
                content_hash="ref-hash",
            )

    collector = TikTokReferenceCollector(repository, Adapter())
    first = collector.collect(
        "42", products, ["https://www.tiktok.com/@creator/video/123"]
    )
    second = collector.collect(
        "42", list(reversed(products)), ["https://www.tiktok.com/@creator/video/123"]
    )

    assert first == second
    assert calls[0][2] == calls[1][2]
    assert first[0].owner_user_id == "42"
    assert first[0].content_hash == "ref-hash"


def test_invalid_tiktok_reference_is_a_permanent_collection_error():
    from hermes.application.affiliate_reference_service import (
        PermanentReferenceError,
        TikTokReferenceCollector,
    )

    class Adapter:
        def fetch(self, *_args):
            raise ValueError("invalid TikTok URL")

    with pytest.raises(PermanentReferenceError):
        TikTokReferenceCollector(object(), Adapter()).collect(
            "42",
            [_product("p1", "1")],
            ["https://evil.test/video/1"],
        )
