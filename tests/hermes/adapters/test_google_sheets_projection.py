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
