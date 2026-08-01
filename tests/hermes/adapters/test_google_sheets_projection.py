from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from hermes.db import Database
from hermes.domain.affiliate_research import AffiliateProduct, ContentPackage, PackageStatus


class FakeSheetsClient:
    def __init__(self):
        self.tabs: dict[str, list[list[object]]] = {}

    def read_rows(self, spreadsheet_id: str, tab_name: str) -> list[list[object]]:
        return [list(row) for row in self.tabs.get(tab_name, [])]

    def replace_rows(self, spreadsheet_id: str, tab_name: str, rows: list[list[object]]) -> None:
        self.tabs[tab_name] = [list(row) for row in rows]

    def row_count(self, tab_name: str) -> int:
        return max(0, len(self.tabs.get(tab_name, [])) - 1)


class FailingSheetsClient:
    def read_rows(self, spreadsheet_id: str, tab_name: str) -> list[list[object]]:
        raise RuntimeError("Sheets service unavailable")

    def replace_rows(self, spreadsheet_id: str, tab_name: str, rows: list[list[object]]) -> None:
        raise RuntimeError("Sheets service unavailable")


class SequencedProjectionRepository:
    def __init__(self, payloads):
        self._payloads = iter(payloads)
        self.calls = []

    def projection_rows(self, owner_user_id: str, run_id: str):
        self.calls.append((owner_user_id, run_id))
        return next(self._payloads)


@pytest.fixture
def repository():
    with TemporaryDirectory(dir=Path.cwd()) as directory:
        database = Database(Path(directory) / "hermes.db")
        database.initialize()
        from hermes.adapters.sqlite.affiliate_research_repository import (
            SQLiteAffiliateResearchRepository,
        )

        repo = SQLiteAffiliateResearchRepository(database)
        product = AffiliateProduct(
            id="product-1", owner_user_id="42", platform="shopee", external_product_id="101",
            name="Ergonomic mouse", category="mouse", price_vnd=300_000, sold_count=120,
            rating=4.8, review_count=40, commission_rate=0.1, shop_name="Example shop",
            product_url="https://example.test/products/101", image_urls=(), visual_signals=(),
            source_type="affiliate_csv", source_url="https://example.test/feed.csv",
            authorization_scope="user_export", rights_status="affiliate_reference", content_hash="hash-101",
            created_at="2026-08-01T00:00:00+00:00", updated_at="2026-08-01T00:00:00+00:00",
        )
        repo.upsert_product(product)
        repo.create_run("run-1", "42", "key-1")
        repo.save_package(
            ContentPackage(
                id="pkg-1", owner_user_id="42", product_id="product-1", run_id="run-1", revision=1,
                status=PackageStatus.PENDING_REVIEW, audience="office_worker", angle="Desk comfort",
                angle_reason="Visible setup improvement", hook="A concise original hook",
                script="An original, evidence-bound script.", duration_seconds=45, storyboard=(), ai_prompts=(),
                voiceover_plan="Vietnamese neutral voice", text_overlays=(), claims=(), warnings=(), asset_rights={},
                created_at="2026-08-01T00:00:00+00:00", updated_at="2026-08-01T00:00:00+00:00",
            )
        )
        yield repo


def test_projection_reconciles_six_tabs_by_stable_id(repository):
    from hermes.adapters.google.sheets_projection import GoogleSheetsProjection

    client = FakeSheetsClient()
    projection = GoogleSheetsProjection(repository, client, "sheet-123")

    result = projection.sync("42", "run-1")

    assert result.ok is True
    assert set(client.tabs) == {
        "Products", "Shortlist", "Ideas", "Scripts", "Approval Queue", "Runs & Errors"
    }
    projection.sync("42", "run-1")
    assert client.row_count("Products") == 1


def test_second_sync_removes_stale_stable_ids_from_another_owner_and_run():
    from hermes.adapters.google.sheets_projection import GoogleSheetsProjection

    empty_rows = {
        "references": [],
        "ideas": [],
        "packages": [],
        "approval_events": [],
    }
    repository = SequencedProjectionRepository(
        [
            {
                **empty_rows,
                "products": [{"id": "old-product", "owner_user_id": "99", "name": "Old"}],
                "runs": [{"id": "old-run", "owner_user_id": "99"}],
            },
            {
                **empty_rows,
                "products": [{"id": "current-product", "owner_user_id": "42", "name": "Current"}],
                "runs": [{"id": "current-run", "owner_user_id": "42"}],
            },
        ]
    )
    client = FakeSheetsClient()
    projection = GoogleSheetsProjection(repository, client, "sheet-123")

    projection.sync("99", "old-run")
    result = projection.sync("42", "current-run")

    assert result.ok is True
    assert [row[0] for row in client.tabs["Products"][1:]] == ["current-product"]
    assert [row[0] for row in client.tabs["Runs & Errors"][1:]] == ["current-run"]
    assert repository.calls == [("99", "old-run"), ("42", "current-run")]


def test_second_sync_preserves_sheet_order_updates_values_drops_stale_and_appends_new():
    from hermes.adapters.google.sheets_projection import GoogleSheetsProjection

    empty_rows = {
        "references": [],
        "ideas": [],
        "packages": [],
        "approval_events": [],
        "runs": [],
    }
    repository = SequencedProjectionRepository(
        [
            {
                **empty_rows,
                "products": [
                    {"id": "second", "name": "Second old"},
                    {"id": "stale", "name": "Stale"},
                    {"id": "first", "name": "First old"},
                ],
            },
            {
                **empty_rows,
                "products": [
                    {"id": "first", "name": "First updated"},
                    {"id": "second", "name": "Second updated"},
                    {"id": "new", "name": "New"},
                ],
            },
        ]
    )
    client = FakeSheetsClient()
    projection = GoogleSheetsProjection(repository, client, "sheet-123")

    projection.sync("42", "run-1")
    result = projection.sync("42", "run-1")

    header, *rows = client.tabs["Products"]
    records = [dict(zip(header, row)) for row in rows]
    assert result.ok is True
    assert header[0] == "stable_id"
    assert [row["stable_id"] for row in records] == ["second", "first", "new"]
    assert [row["name"] for row in records] == ["Second updated", "First updated", "New"]


def test_sheet_outage_returns_retryable_result_without_changing_sqlite(repository):
    from hermes.adapters.google.sheets_projection import GoogleSheetsProjection

    projection = GoogleSheetsProjection(repository, FailingSheetsClient(), "sheet-123")

    result = projection.sync("42", "run-1")

    assert result.ok is False
    assert result.retryable is True
    assert repository.get_package("pkg-1", "42") is not None


def test_disabled_and_fake_projections_are_safe_local_adapters():
    from hermes.adapters.google.sheets_projection import (
        DisabledSheetsProjection,
        FakeSheetsProjection,
    )

    fake = FakeSheetsProjection()

    assert DisabledSheetsProjection().sync("42", "run-1").detail == "disabled"
    assert fake.sync("42", "run-1").detail == "fake"
    assert fake.calls == [("42", "run-1")]


def test_environment_factory_requires_configuration_without_loading_credentials(monkeypatch, repository):
    from hermes.adapters.google.sheets_projection import GoogleSheetsProjection

    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_FILE", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_SHEETS_CREDENTIALS_FILE"):
        GoogleSheetsProjection.from_environment(repository)


def test_operator_editable_columns_survive_resync():
    from hermes.adapters.google.sheets_projection import GoogleSheetsProjection

    payload = {
        "products": [{"id": "p1", "name": "Canonical"}],
        "references": [],
        "ideas": [],
        "packages": [],
        "approval_events": [],
        "runs": [],
    }
    client = FakeSheetsClient()
    projection = GoogleSheetsProjection(
        SequencedProjectionRepository([payload, payload]), client, "sheet-123"
    )
    projection.sync("42", "run-1")
    header = client.tabs["Products"][0]
    client.tabs["Products"][0] = [*header, "review_notes", "custom_priority"]
    client.tabs["Products"][1] = [
        *client.tabs["Products"][1],
        "Keep this note",
        "P1",
    ]

    projection.sync("42", "run-1")

    header, row = client.tabs["Products"]
    record = dict(zip(header, row))
    assert record["name"] == "Canonical"
    assert record["review_notes"] == "Keep this note"
    assert record["custom_priority"] == "P1"
