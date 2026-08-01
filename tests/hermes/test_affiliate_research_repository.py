from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from hermes.db import Database
from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ContentIdea,
    ContentPackage,
    PackageStatus,
    ReferenceMetadata,
    ScoreBreakdown,
)


@pytest.fixture
def database():
    with TemporaryDirectory(dir=Path.cwd()) as directory:
        value = Database(Path(directory) / "hermes.db")
        value.initialize()
        yield value


@pytest.fixture
def product() -> AffiliateProduct:
    return AffiliateProduct(
        id="product-1",
        owner_user_id="42",
        platform="shopee",
        external_product_id="101",
        name="Ergonomic mouse",
        category="mouse",
        price_vnd=300_000,
        sold_count=120,
        rating=4.8,
        review_count=40,
        commission_rate=0.1,
        shop_name="Example shop",
        product_url="https://example.test/products/101",
        image_urls=("https://example.test/mouse.jpg",),
        visual_signals=("light", "visible_problem_solution"),
        source_type="affiliate_csv",
        source_url="https://example.test/feed.csv",
        authorization_scope="user_export",
        rights_status="affiliate_reference",
        content_hash="hash-101",
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )


def package(*, package_id: str = "package-1", revision: int = 1, **overrides) -> ContentPackage:
    value = ContentPackage(
        id=package_id,
        owner_user_id="42",
        product_id="product-1",
        run_id="run-1",
        revision=revision,
        status=PackageStatus.PENDING_REVIEW,
        audience="office_worker",
        angle="Desk comfort",
        angle_reason="Visible setup improvement",
        hook="A concise original hook",
        script="An original, evidence-bound script.",
        duration_seconds=45,
        storyboard=({"start": 0, "end": 5, "visual": "Mouse on desk"},),
        ai_prompts=("Modern desk",),
        voiceover_plan="Vietnamese neutral voice",
        text_overlays=("More desk space",),
        claims=({"text": "Wireless", "evidence_url": "https://example.test/products/101"},),
        warnings=("Verify current price",),
        asset_rights={"product-1": "affiliate_reference"},
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )
    return replace(value, **overrides)


def reference(**overrides) -> ReferenceMetadata:
    value = ReferenceMetadata(
        id="reference-1",
        owner_user_id="42",
        product_id="product-1",
        platform="tiktok",
        source_url="https://example.test/reference/1",
        title="Reference title",
        author_name="Creator",
        author_url="https://example.test/creator",
        thumbnail_url="https://example.test/thumb.jpg",
        caption="Reference caption",
        embed_html="<blockquote></blockquote>",
        authorization_scope="public_metadata",
        rights_status="reference_only",
        media_local_path="",
        collected_at="2026-08-01T00:00:00+00:00",
    )
    return replace(value, **overrides)


def repository(database):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )

    return SQLiteAffiliateResearchRepository(database)


def test_upsert_and_snapshot_are_idempotent(database, product):
    repo = repository(database)

    first = repo.upsert_product(product)
    second = repo.upsert_product(
        replace(
            product,
            name="Updated mouse",
            source_type="manual",
            source_url="https://example.test/product/101",
            authorization_scope="owner_submission",
            rights_status="licensed_reference",
        )
    )
    repo.record_snapshot(first.id, "2026-08-01", product)
    repo.record_snapshot(first.id, "2026-08-01", product)

    assert first.id == second.id == product.id
    assert [item.name for item in repo.list_products("42")] == ["Updated mouse"]
    assert second.source_type == "manual"
    assert second.source_url == "https://example.test/product/101"
    assert second.authorization_scope == "owner_submission"
    assert second.rights_status == "licensed_reference"
    assert len(repo.list_snapshots(first.id)) == 1


def test_package_lookup_is_owner_scoped_and_revisions_are_preserved(database, product):
    repo = repository(database)
    repo.upsert_product(product)
    repo.create_run("run-1", "42", "key-1")
    first = repo.save_package(package())
    revision = repo.save_package(package(package_id="package-2", revision=2))

    assert repo.get_package(first.id, "99") is None
    assert repo.get_package(first.id, "42") == first
    assert repo.get_package(revision.id, "42") == revision

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT id, revision FROM affiliate_content_packages ORDER BY revision"
        ).fetchall()
    assert [(row["id"], row["revision"]) for row in rows] == [
        ("package-1", 1),
        ("package-2", 2),
    ]


def test_list_packages_filters_by_owner_and_optional_run_in_deterministic_order(database, product):
    repo = repository(database)
    repo.upsert_product(product)
    repo.create_run("run-1", "42", "key-1")
    repo.create_run("run-2", "42", "key-2")
    repo.save_package(package(package_id="later", created_at="2026-08-01T00:00:02+00:00"))
    repo.save_package(
        package(
            package_id="earlier",
            run_id="run-2",
            created_at="2026-08-01T00:00:01+00:00",
        )
    )

    assert [item.id for item in repo.list_packages("42")] == ["later", "earlier"]
    assert [item.id for item in repo.list_packages("42", "run-2")] == ["earlier"]
    assert repo.list_packages("99") == []


def test_save_package_rejects_conflicting_retry_payload(database, product):
    repo = repository(database)
    repo.upsert_product(product)
    repo.create_run("run-1", "42", "key-1")
    saved = repo.save_package(package())

    assert repo.save_package(package()) == saved
    with pytest.raises(ValueError, match="conflicting package payload"):
        repo.save_package(package(revision=2))
    with pytest.raises(ValueError, match="conflicting package payload"):
        repo.save_package(package(hook="A changed retry payload"))

    assert repo.get_package(saved.id, "42") == saved
    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM affiliate_content_packages").fetchone()[0]
    assert count == 1


@pytest.mark.parametrize(
    ("action", "status"),
    [
        ("approve", PackageStatus.APPROVED),
        ("revise", PackageStatus.REVISION_REQUESTED),
        ("reject", PackageStatus.REJECTED),
    ],
)
def test_transition_package_appends_one_event_and_is_idempotent(database, product, action, status):
    repo = repository(database)
    repo.upsert_product(product)
    repo.create_run("run-1", "42", "key-1")
    saved = repo.save_package(package())

    transitioned = repo.transition_package(saved.id, "42", action, "review decision")
    repeated = repo.transition_package(saved.id, "42", action, "duplicate callback")

    assert transitioned.status is status
    assert repeated == transitioned
    with database.connect() as connection:
        events = connection.execute(
            "SELECT action, reason FROM affiliate_approval_events WHERE package_id = ?",
            (saved.id,),
        ).fetchall()
    assert [(event["action"], event["reason"]) for event in events] == [
        (action, "review decision")
    ]


def test_package_transition_rolls_back_when_event_insert_fails(database, product):
    repo = repository(database)
    repo.upsert_product(product)
    repo.create_run("run-1", "42", "key-1")
    saved = repo.save_package(package())
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_affiliate_event_insert
            BEFORE INSERT ON affiliate_approval_events
            BEGIN
                SELECT RAISE(ABORT, 'forced event insert failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced event insert failure"):
        repo.transition_package(saved.id, "42", "approve", "review decision")

    assert repo.get_package(saved.id, "42") == saved
    with database.connect() as connection:
        event_count = connection.execute(
            "SELECT COUNT(*) FROM affiliate_approval_events WHERE package_id = ?",
            (saved.id,),
        ).fetchone()[0]
    assert event_count == 0


def test_child_records_reject_cross_owner_parents_without_partial_writes(database, product):
    repo = repository(database)
    repo.upsert_product(product)
    repo.upsert_product(replace(product, id="product-2", owner_user_id="99", external_product_id="202"))
    repo.create_run("run-1", "42", "key-1")
    repo.create_run("run-2", "99", "key-2")
    idea = ContentIdea(
        id="idea-1",
        owner_user_id="42",
        product_id=product.id,
        run_id="run-2",
        audience="office_worker",
        angle="Desk comfort",
        rationale="Visible benefit",
        created_at="2026-08-01T00:00:00+00:00",
    )

    with pytest.raises(LookupError, match="does not belong to owner"):
        repo.save_reference(reference(product_id="product-2"))
    with pytest.raises(LookupError, match="does not belong to owner"):
        repo.save_ideas(product.id, "run-2", [idea])
    with pytest.raises(LookupError, match="does not belong to owner"):
        repo.save_package(package(product_id="product-2"))
    with pytest.raises(LookupError, match="does not belong to owner"):
        repo.save_package(package(package_id="package-2", run_id="run-2"))

    with database.connect() as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("affiliate_references", "affiliate_content_ideas", "affiliate_content_packages")
        }
    assert counts == {
        "affiliate_references": 0,
        "affiliate_content_ideas": 0,
        "affiliate_content_packages": 0,
    }


def test_repository_persists_score_reference_ideas_runs_and_projection_rows(database, product):
    repo = repository(database)
    repo.upsert_product(product)
    repo.create_run("run-1", "42", "key-1")
    repo.save_score(
        product.id,
        ScoreBreakdown(82.5, {"sales": 45.0}, "strong sales", "high", 0.2),
        "shortlisted",
    )
    saved_reference = reference()
    idea = ContentIdea(
        id="idea-1",
        owner_user_id="42",
        product_id=product.id,
        run_id="run-1",
        audience="office_worker",
        angle="Desk comfort",
        rationale="Visible benefit",
        created_at="2026-08-01T00:00:00+00:00",
    )

    assert repo.save_reference(saved_reference) == saved_reference
    assert repo.save_ideas(product.id, "run-1", [idea]) == [idea]
    assert repo.create_run("run-2", "42", "key-1")["id"] == "run-1"
    assert repo.finish_run("run-1", {"imported": 1, "shortlisted": 1})["status"] == "completed"

    rows = repo.projection_rows("42", "run-1")
    assert rows["products"][0]["eligibility_status"] == "shortlisted"
    assert rows["ideas"][0]["id"] == idea.id
    assert rows["references"][0]["id"] == saved_reference.id
    assert rows["runs"][0]["counters"] == {"imported": 1, "shortlisted": 1}


def test_projection_failures_are_persisted_and_cleared_without_new_table(database):
    repo = repository(database)
    repo.create_run("run-1", "42", "key-1")
    repo.finish_run("run-1", {"imported": 1, "shortlisted": 1, "packaged": 0})

    recorded = repo.record_projection_failure("run-1", "sheets", "outage", retryable=True)

    assert recorded["counters"]["projection_failures"] == {
        "sheets": {"detail": "outage", "retryable": True}
    }
    cleared = repo.clear_projection_failure("run-1", "sheets")
    assert "projection_failures" not in cleared["counters"]
