from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest
from types import SimpleNamespace

from hermes.db import Database
from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ContentPackage,
    PackageStatus,
    ReferenceMetadata,
    ScoreBreakdown,
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


def test_v5_migration_creates_run_catalog_outbox_and_provenance(tmp_path):
    database = Database(tmp_path / "hermes.db")
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
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
        "affiliate_projection_items",
        "affiliate_research_briefs",
    } <= tables
    assert {"source_type", "content_hash"} <= reference_columns
    with database.connect() as connection:
        run_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(affiliate_run_products)"
            )
        }
    assert {
        "eligibility_status",
        "score",
        "score_json",
        "score_reason",
        "score_confidence",
        "rank",
        "shortlisted",
        "evidence_ids_json",
        "snapshot_timestamps_json",
    } <= run_columns
    with database.connect() as connection:
        brief_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(affiliate_research_briefs)"
            )
        }
    assert "reference_pattern_provenance_json" in brief_columns


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


def test_later_run_score_does_not_mutate_older_projection(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    product = repository.upsert_product(_product("p1", "1"))
    for run_id in ("run-1", "run-2"):
        repository.create_run(run_id, "42", f"key-{run_id}")
        repository.record_run_product(run_id, product.id)
    first = ScoreBreakdown(
        81.0,
        {"sales": 40.0},
        "run one evidence",
        "high",
        0.1,
        evidence_ids=("source:42:p1:hash-1", "snapshot:42:p1:2026-08-01"),
        snapshot_timestamps=("2026-08-01T00:00:00+00:00",),
    )
    second = ScoreBreakdown(
        22.0,
        {"sales": 5.0},
        "run two evidence",
        "low",
        None,
        evidence_ids=("source:42:p1:hash-2", "snapshot:42:p1:2026-08-02"),
        snapshot_timestamps=("2026-08-02T00:00:00+00:00",),
    )

    repository.save_run_score(
        "run-1", product.id, first, "shortlisted", rank=1, shortlisted=True
    )
    before = repository.projection_rows("42", "run-1")["products"][0]
    repository.save_run_score(
        "run-2", product.id, second, "eligible", rank=8, shortlisted=False
    )
    after = repository.projection_rows("42", "run-1")["products"][0]

    assert after == before
    assert after["score"] == 81.0
    assert after["rank"] == 1
    assert after["shortlisted"] == 1
    assert after["evidence_ids"] == [
        "source:42:p1:hash-1",
        "snapshot:42:p1:2026-08-01",
    ]
    assert repository.list_products("42", "run-2")[0].score == 22.0


def test_catalog_score_persists_owner_scoped_source_and_snapshot_evidence(tmp_path):
    from hermes.adapters.affiliate.manual_source import ManualProductSource
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )
    from hermes.application.affiliate_catalog_service import AffiliateCatalogService
    from hermes.domain.affiliate_research import ProductCandidate

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    repository.create_run("run-1", "42", "key-1")
    candidate = ProductCandidate(
        owner_user_id="42",
        platform="shopee",
        external_product_id="1",
        name="Evidence Mouse",
        category="mouse",
        price_vnd=300_000,
        sold_count=100,
        rating=4.8,
        review_count=20,
        commission_rate=0.1,
        shop_name="Shop",
        product_url="https://example.test/1",
        image_urls=("https://example.test/1.jpg",),
        visual_signals=("movement",),
        source_type="affiliate_csv",
        source_url="https://example.test/feed.csv",
        authorization_scope="user_export",
        rights_status="affiliate_reference",
        content_hash="source-hash-1",
    )
    catalog = AffiliateCatalogService(repository)
    catalog.import_candidates(
        ManualProductSource([candidate]),
        owner_user_id="42",
        run_id="run-1",
        snapshot_date="2026-08-01",
    )
    catalog.score_and_shortlist(
        owner_user_id="42", run_id="run-1", minimum=15, maximum=25
    )

    row = repository.projection_rows("42", "run-1")["products"][0]
    assert any(value.startswith("source:42:") for value in row["evidence_ids"])
    assert any(value.startswith("snapshot:42:") for value in row["evidence_ids"])
    assert row["snapshot_timestamps"]
    assert row["score_confidence"] in {"low", "medium", "high"}


def test_reference_patterns_and_angles_are_abstract_and_evidence_specific():
    from hermes.application.affiliate_content_service import AffiliateContentService

    first_product = _product("p1", "1")
    second_product = _product("p2", "2")

    def reference(product_id, reference_id, raw_title, content_hash):
        return ReferenceMetadata(
            id=reference_id,
            owner_user_id="42",
            product_id=product_id,
            platform="tiktok",
            source_url=f"https://www.tiktok.com/@creator/video/{reference_id}",
            title=raw_title,
            author_name="Creator",
            author_url="",
            thumbnail_url="",
            caption=f"{raw_title} raw caption",
            embed_html="",
            authorization_scope="public_oembed",
            rights_status="reference_only",
            media_local_path="",
            collected_at="2026-08-01T00:00:00+00:00",
            source_type="tiktok_oembed",
            content_hash=content_hash,
        )

    first_reference = reference(
        "p1",
        "ref-1",
        "COPY THIS TITLE before and after a cluttered desk",
        "ref-hash-1",
    )
    second_reference = reference(
        "p2",
        "ref-2",
        "ANOTHER RAW TITLE compare mouse A versus mouse B",
        "ref-hash-2",
    )
    first_brief = AffiliateContentService._brief_for(
        first_product, "42", "run-1", [first_reference]
    )
    second_brief = AffiliateContentService._brief_for(
        second_product, "42", "run-1", [second_reference]
    )
    first_ideas = AffiliateContentService._ideas_for(
        first_product, "42", "run-1", first_brief
    )
    second_ideas = AffiliateContentService._ideas_for(
        second_product, "42", "run-1", second_brief
    )
    alternate_brief = AffiliateContentService._brief_for(
        first_product, "42", "run-1", [second_reference]
    )
    alternate_ideas = AffiliateContentService._ideas_for(
        first_product, "42", "run-1", alternate_brief
    )

    assert all(
        "COPY THIS TITLE" not in str(value)
        for value in first_brief.reference_patterns
    )
    assert all(
        "ANOTHER RAW TITLE" not in str(value)
        for value in second_brief.reference_patterns
    )
    assert first_brief.reference_patterns != second_brief.reference_patterns
    assert 3 <= len(first_ideas) <= 5
    assert [idea.rank for idea in first_ideas] == [1, 2, 3]
    assert sum(idea.selected for idea in first_ideas) == 1
    assert {idea.angle for idea in first_ideas}.isdisjoint(
        {idea.angle for idea in second_ideas}
    )
    assert {idea.angle for idea in first_ideas}.isdisjoint(
        {idea.angle for idea in alternate_ideas}
    )


def test_telegram_crash_after_first_send_retries_only_unresolved_package(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )
    from hermes.adapters.telegram.affiliate_review import TelegramReviewDelivery
    from hermes.application.affiliate_content_service import AffiliateContentService

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    repository.create_run("run-1", "42", "key-1")
    products = [
        repository.upsert_product(_product("p1", "1")),
        repository.upsert_product(_product("p2", "2")),
    ]
    package_ids = [
        AffiliateContentService._initial_package_id("42", "run-1", product.id)
        for product in products
    ]
    for package_id, product in zip(package_ids, products):
        repository.record_run_product("run-1", product.id)
        repository.save_package(
            ContentPackage(
                id=package_id,
                owner_user_id="42",
                product_id=product.id,
                run_id="run-1",
                revision=1,
                status=PackageStatus.PENDING_REVIEW,
                audience="office_worker",
                angle=f"Angle for {product.external_product_id}",
                angle_reason="Evidence-derived reason",
                hook=f"Hook for {product.external_product_id}",
                script=f"Script for {product.external_product_id}",
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
        )
    repository.complete_run(
        "run-1",
        {"packaged": 2},
        ("telegram",),
        projection_items={"telegram": tuple(package_ids)},
    )

    class CrashAfterFirstBot:
        def __init__(self):
            self.calls = []

        def send_photo(self, **kwargs):
            self.calls.append(kwargs["caption"])
            if len(self.calls) == 2:
                raise RuntimeError("injected crash")
            return SimpleNamespace(message_id=101)

        def send_message(self, **_kwargs):
            raise RuntimeError("injected crash")

    first_bot = CrashAfterFirstBot()
    first = TelegramReviewDelivery(
        repository, first_bot, chat_id="42"
    ).send_pending("42", package_ids)

    assert first.ok is False
    assert repository.pending_projection_items(
        "run-1", "telegram", package_ids
    ) == [package_ids[1]]
    with repository._database.connect() as connection:
        first_checkpoint = connection.execute(
            """
            SELECT status, external_message_id
            FROM affiliate_projection_items
            WHERE run_id = ? AND projection = 'telegram' AND item_id = ?
            """,
            ("run-1", package_ids[0]),
        ).fetchone()
    assert tuple(first_checkpoint) == ("delivered", "101")

    class SuccessBot:
        def __init__(self):
            self.calls = []

        def send_photo(self, **kwargs):
            self.calls.append(kwargs["caption"])
            return SimpleNamespace(message_id=202)

    retry_bot = SuccessBot()
    second = TelegramReviewDelivery(
        repository, retry_bot, chat_id="42"
    ).send_pending("42", package_ids)

    assert second.ok is True
    assert len(retry_bot.calls) == 1
    assert package_ids[1] in retry_bot.calls[0]
    assert repository.pending_projection_items(
        "run-1", "telegram", package_ids
    ) == []
    with repository._database.connect() as connection:
        second_message_id = connection.execute(
            """
            SELECT external_message_id
            FROM affiliate_projection_items
            WHERE run_id = ? AND projection = 'telegram' AND item_id = ?
            """,
            ("run-1", package_ids[1]),
        ).fetchone()[0]
    assert second_message_id == "202"


def test_telegram_creates_missing_checkpoint_before_external_send(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )
    from hermes.adapters.telegram.affiliate_review import TelegramReviewDelivery
    from hermes.application.affiliate_content_service import AffiliateContentService

    database = Database(tmp_path / "hermes.db")
    repository = SQLiteAffiliateResearchRepository(database)
    repository.create_run("run-1", "42", "key-1")
    product = repository.upsert_product(_product("p1", "1"))
    repository.record_run_product("run-1", product.id)
    package_id = AffiliateContentService._initial_package_id(
        "42", "run-1", product.id
    )
    repository.save_package(
        ContentPackage(
            id=package_id,
            owner_user_id="42",
            product_id=product.id,
            run_id="run-1",
            revision=1,
            status=PackageStatus.PENDING_REVIEW,
            audience="office_worker",
            angle="Evidence angle",
            angle_reason="Evidence reason",
            hook="Evidence hook",
            script="Evidence script",
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
    )
    repository.complete_run("run-1", {"packaged": 1}, ("telegram",))

    class InspectingBot:
        def send_photo(self, **_kwargs):
            with database.connect() as connection:
                checkpoint = connection.execute(
                    """
                    SELECT status FROM affiliate_projection_items
                    WHERE run_id = 'run-1' AND projection = 'telegram'
                      AND item_id = ?
                    """,
                    (package_id,),
                ).fetchone()
            assert checkpoint is not None
            assert checkpoint["status"] == "pending"
            return SimpleNamespace(message_id=303)

    result = TelegramReviewDelivery(
        repository, InspectingBot(), chat_id="42"
    ).send_pending("42", [package_id])

    assert result.ok is True
    with database.connect() as connection:
        checkpoint = connection.execute(
            """
            SELECT status, external_message_id
            FROM affiliate_projection_items
            WHERE run_id = 'run-1' AND projection = 'telegram'
              AND item_id = ?
            """,
            (package_id,),
        ).fetchone()
    assert tuple(checkpoint) == ("delivered", "303")


def test_pre_v5_raw_brief_upgrade_and_fault_retry_becomes_structured(
    tmp_path,
):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )
    from hermes.adapters.sqlite.schema_v2 import apply_schema_v2
    from hermes.adapters.sqlite.schema_v4 import apply_schema_v4
    from hermes.application.affiliate_content_service import AffiliateContentService
    from hermes.db import SCHEMA_V1, SCHEMA_V3

    path = tmp_path / "hermes.db"
    brief_id = hashlib.sha256(
        "42\0run-legacy\0p1\0brief\0r1".encode("utf-8")
    ).hexdigest()
    raw_pattern = "COPY THIS RAW TITLE AND CAPTION"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA_V1)
        apply_schema_v2(connection)
        connection.executescript(SCHEMA_V3)
        apply_schema_v4(connection)
        connection.execute(
            """
            INSERT INTO affiliate_products(
                id, owner_user_id, platform, external_product_id, name,
                category, price_vnd, sold_count, rating, review_count,
                commission_rate, shop_name, product_url, image_urls_json,
                visual_signals_json, source_type, source_url,
                authorization_scope, rights_status, content_hash,
                created_at, updated_at
            ) VALUES (
                'p1', '42', 'shopee', '1', 'Product 1', 'mouse', 300000,
                100, 4.8, 20, 0.1, 'Shop', 'https://example.test/1',
                '["https://example.test/1.jpg"]', '["movement"]',
                'affiliate_csv', 'https://example.test/feed.csv',
                'user_export', 'affiliate_reference', 'hash-1',
                '2026-08-01T00:00:00+00:00',
                '2026-08-01T00:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO affiliate_research_runs(
                id, owner_user_id, idempotency_key, status, counters_json,
                created_at, updated_at
            ) VALUES (
                'run-legacy', '42', 'legacy-key', 'running', '{}',
                '2026-08-01T00:00:00+00:00',
                '2026-08-01T00:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO affiliate_run_products(
                run_id, product_id, observation_status, warnings_json,
                observed_at
            ) VALUES (
                'run-legacy', 'p1', 'imported', '[]',
                '2026-08-01T00:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO affiliate_references(
                id, owner_user_id, product_id, platform, source_url, title,
                author_name, author_url, thumbnail_url, caption, embed_html,
                authorization_scope, rights_status, media_local_path,
                collected_at, source_type, content_hash
            ) VALUES (
                'ref-legacy', '42', 'p1', 'tiktok',
                'https://example.test/ref-legacy',
                'Before and after fixing a cluttered desk', 'Creator', '', '',
                'First show the problem, then reveal the clean setup', '',
                'public_metadata', 'reference_only', '',
                '2026-08-01T00:00:00+00:00', 'tiktok_oembed',
                'ref-hash-legacy'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO affiliate_research_briefs(
                id, owner_user_id, product_id, run_id, revision,
                verified_specs_json, strengths_json, limitations_json,
                unverified_claims_json, reference_patterns_json, created_at
            ) VALUES (?, '42', 'p1', 'run-legacy', 1, '[]', '[]', '[]',
                      '[]', ?, '2026-08-01T00:00:00+00:00')
            """,
            (brief_id, json.dumps([raw_pattern])),
        )
        connection.execute("PRAGMA user_version = 4")
        connection.commit()
    finally:
        connection.close()

    database = Database(path)
    database.initialize()
    with database.connect() as upgraded:
        migrated = upgraded.execute(
            """
            SELECT reference_patterns_json,
                   reference_pattern_provenance_json
            FROM affiliate_research_briefs WHERE id = ?
            """,
            (brief_id,),
        ).fetchone()
    assert json.loads(migrated["reference_patterns_json"]) == []
    assert raw_pattern not in migrated["reference_patterns_json"]

    product = _product("p1", "1")
    reference = ReferenceMetadata(
        id="ref-legacy",
        owner_user_id="42",
        product_id="p1",
        platform="tiktok",
        source_url="https://example.test/ref-legacy",
        title="Before and after fixing a cluttered desk",
        author_name="Creator",
        author_url="",
        thumbnail_url="",
        caption="First show the problem, then reveal the clean setup",
        embed_html="",
        authorization_scope="public_metadata",
        rights_status="reference_only",
        media_local_path="",
        collected_at="2026-08-01T00:00:00+00:00",
        source_type="tiktok_oembed",
        content_hash="ref-hash-legacy",
    )

    class FailOnceGateway:
        def __init__(self):
            self.calls = []

        def generate(
            self, _product, _references, *, brief, selected_idea
        ):
            self.calls.append((brief, selected_idea))
            if len(self.calls) == 1:
                raise RuntimeError("injected post-brief failure")
            return {
                "audience": "office_worker",
                "angle": "Structured angle",
                "angle_reason": "Structured evidence",
                "hook": "Observe the desk change.",
                "script": "Show the product and the resulting desk layout.",
                "duration_seconds": 45,
                "storyboard": [
                    {"start": 0, "end": 5, "visual": "Product on desk"}
                ],
                "ai_prompts": ["Use the supplied product image"],
                "voiceover_plan": "Neutral",
                "text_overlays": ["Desk change"],
                "claims": [
                    {
                        "text": "Canonical product information",
                        "evidence_url": product.product_url,
                    }
                ],
                "warnings": [],
            }

    repository = SQLiteAffiliateResearchRepository(database)
    gateway = FailOnceGateway()
    service = AffiliateContentService(repository, gateway)
    with pytest.raises(RuntimeError, match="post-brief"):
        service.create_packages(
            "42",
            "run-legacy",
            [product],
            [reference],
            per_run=5,
        )

    packages = service.create_packages(
        "42", "run-legacy", [product], [reference], per_run=5
    )
    repeated = service.create_packages(
        "42", "run-legacy", [product], [reference], per_run=5
    )

    assert repeated == packages
    assert len(gateway.calls) == 2
    first_brief, second_brief = (
        gateway.calls[0][0],
        gateway.calls[1][0],
    )
    assert first_brief == second_brief
    assert all(
        set(pattern) == {"hook", "pacing", "story"}
        for pattern in first_brief.reference_patterns
    )
    assert first_brief.reference_pattern_provenance[0][
        "reference_id"
    ] == "ref-legacy"
    with database.connect() as persisted:
        row = persisted.execute(
            """
            SELECT reference_patterns_json,
                   reference_pattern_provenance_json
            FROM affiliate_research_briefs WHERE id = ?
            """,
            (brief_id,),
        ).fetchone()
    assert raw_pattern not in row["reference_patterns_json"]
    assert all(
        isinstance(item, dict)
        for item in json.loads(row["reference_patterns_json"])
    )
    assert json.loads(row["reference_pattern_provenance_json"])[0][
        "reference_id"
    ] == "ref-legacy"
