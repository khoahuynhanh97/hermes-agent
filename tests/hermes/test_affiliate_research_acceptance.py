from __future__ import annotations

import csv

import pytest
import requests
import telegram

from hermes.db import Database
from hermes.domain.affiliate_research import ProjectionResult


class DeterministicContentGateway:
    """Offline content fixture; it deliberately has no model or network dependency."""

    def generate(self, product, references):
        product_number = product.external_product_id
        unique_terms = " ".join(f"term{product_number}{index}" for index in range(1, 7))
        return {
            "audience": "technology shoppers",
            "angle": f"workspace improvement {product_number}",
            "angle_reason": "The authorized feed provides product details and images.",
            "hook": f"{unique_terms} desk product introduction",
            "script": (
                f"{unique_terms} show the authorized product listing and ask viewers to verify "
                "the current offer before acting."
            ),
            "duration_seconds": 45,
            "storyboard": [
                {"start": 0, "end": 15, "visual": "Product close-up"},
                {"start": 15, "end": 30, "visual": "Desk setup context"},
                {"start": 30, "end": 45, "visual": "Authorized product listing"},
            ],
            "ai_prompts": [f"Generate an original product scene for {product_number}."],
            "voiceover_plan": "Neutral factual voiceover.",
            "text_overlays": ["Check the current listing details."],
            "claims": [
                {
                    "text": f"The authorized listing identifies product {product_number}.",
                    "evidence_url": product.product_url,
                }
            ],
            "warnings": ["Verify price and availability before publishing."],
        }


class FakeSheetsProjection:
    def __init__(self):
        self.calls = []

    def sync(self, owner_user_id, run_id):
        self.calls.append((owner_user_id, run_id))
        return ProjectionResult(ok=True, retryable=False, detail="fake")


class FakeReviewDelivery:
    def __init__(self):
        self.sent_package_ids = []

    def send_pending(self, owner_user_id, package_ids):
        self.sent_package_ids.extend(package_ids)
        return ProjectionResult(ok=True, retryable=False, detail="fake")


class OfflineHarness:
    def __init__(self, database_path, content_gateway, sheets, review_delivery):
        from hermes.adapters.sqlite.affiliate_research_repository import (
            SQLiteAffiliateResearchRepository,
        )
        from hermes.application.affiliate_catalog_service import AffiliateCatalogService
        from hermes.application.affiliate_content_service import AffiliateContentService
        from hermes.application.affiliate_run_service import AffiliateRunRequest, AffiliateRunService

        self.repository = SQLiteAffiliateResearchRepository(Database(database_path))
        self.sheets = sheets
        self.review_delivery = review_delivery
        self._request_type = AffiliateRunRequest
        self._service = AffiliateRunService(
            self.repository,
            AffiliateCatalogService(self.repository),
            AffiliateContentService(self.repository, content_gateway),
            sheets_projection=sheets,
            review_delivery=review_delivery,
            snapshot_date=lambda: "2026-08-01",
        )

    def run(self, owner_user_id, idempotency_key, csv_path, package_limit):
        return self._service.run(
            self._request_type(
                owner_user_id=owner_user_id,
                idempotency_key=idempotency_key,
                csv_path=str(csv_path),
                package_limit=package_limit,
            )
        )


def build_offline_harness(**kwargs):
    return OfflineHarness(**kwargs)


def write_200_authorized_products(path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "item_id",
                "product_name",
                "category",
                "price",
                "sold",
                "rating",
                "review_count",
                "commission",
                "shop_name",
                "product_link",
                "image",
                "visual_signals",
            ),
        )
        writer.writeheader()
        for number in range(1, 201):
            writer.writerow(
                {
                    "item_id": str(number),
                    "product_name": f"Workspace mouse {number}",
                    "category": "mouse",
                    "price": "350000",
                    "sold": str(10_000 + number),
                    "rating": "4.8",
                    "review_count": str(1_000 + number),
                    "commission": "12%",
                    "shop_name": "Authorized Shop",
                    "product_link": f"https://example.test/products/{number}",
                    "image": f"https://example.test/images/{number}.jpg",
                    "visual_signals": "light|visible_problem_solution|multiple_scenes",
                }
            )
    return path


def _external_tripwire(*_args, **_kwargs):
    raise AssertionError("offline acceptance must not invoke an external integration")


def test_200_product_run_is_idempotent_and_produces_review_packages(tmp_path, monkeypatch):
    import hermes.adapters.google.sheets_projection as sheets_module
    import hermes.llm as llm_module

    monkeypatch.setattr(requests, "request", _external_tripwire)
    monkeypatch.setattr(requests.Session, "request", _external_tripwire)
    monkeypatch.setattr(llm_module, "HermesLLMGateway", _external_tripwire)
    monkeypatch.setattr(
        sheets_module._GoogleSheetsClient,
        "from_credentials_file",
        classmethod(_external_tripwire),
    )
    monkeypatch.setattr(telegram, "Bot", _external_tripwire)

    fixture = write_200_authorized_products(tmp_path / "products.csv")
    harness = build_offline_harness(
        database_path=tmp_path / "hermes.db",
        content_gateway=DeterministicContentGateway(),
        sheets=FakeSheetsProjection(),
        review_delivery=FakeReviewDelivery(),
    )

    first = harness.run("42", "daily-2026-08-01", fixture, package_limit=10)
    second = harness.run("42", "daily-2026-08-01", fixture, package_limit=10)

    assert first.imported == 200
    assert 15 <= first.shortlisted <= 25
    assert 5 <= len(first.package_ids) <= 10
    assert second.reused is True
    assert len(harness.repository.list_products("42")) == 200
    assert harness.sheets.calls == [("42", first.run_id)]
    assert harness.review_delivery.sent_package_ids == list(first.package_ids)

    packages = harness.repository.list_packages("42", run_id=first.run_id)
    assert len(packages) == len(first.package_ids)
    for package in packages:
        assert 30 <= package.duration_seconds <= 90
        assert package.script
        assert package.storyboard
        assert package.ai_prompts
        assert package.warnings
        assert package.asset_rights
        assert all(claim["evidence_url"].startswith("https://") for claim in package.claims)


def test_affiliate_configuration_validates_limits_and_redacts_credentials(tmp_path):
    from hermes.affiliate_config import load_affiliate_research_settings

    settings = load_affiliate_research_settings(
        {
            "AFFILIATE_IMPORT_DIR": str(tmp_path / "imports"),
            "GOOGLE_SHEETS_ENABLED": "0",
            "GOOGLE_SHEETS_CREDENTIALS_FILE": "secret-service-account.json",
            "GOOGLE_SHEETS_SPREADSHEET_ID": "spreadsheet-id",
            "AFFILIATE_RESEARCH_SHORTLIST_LIMIT": "15",
            "AFFILIATE_RESEARCH_PACKAGE_LIMIT": "5",
        }
    )

    assert settings.import_directory == (tmp_path / "imports").resolve()
    assert settings.google_sheets_enabled is False
    assert settings.shortlist_limit == 15
    assert settings.package_limit == 5
    assert "secret-service-account.json" not in repr(settings)

    with pytest.raises(ValueError) as error:
        load_affiliate_research_settings(
            {
                "AFFILIATE_RESEARCH_SHORTLIST_LIMIT": "26",
                "GOOGLE_SHEETS_CREDENTIALS_FILE": "secret-service-account.json",
            }
        )
    assert "secret-service-account.json" not in str(error.value)


def test_production_composition_disables_external_projections_when_not_configured(monkeypatch, tmp_path):
    import core.affiliate_research_jobs as jobs
    import hermes.adapters.google.sheets_projection as sheets_module
    import hermes.adapters.model.affiliate_content_gateway as content_gateway_module
    import hermes.adapters.sqlite.affiliate_research_repository as repository_module
    import hermes.application.affiliate_catalog_service as catalog_module
    import hermes.application.affiliate_content_service as content_module
    import hermes.db as database_module
    import hermes.llm as llm_module
    from hermes.affiliate_config import AffiliateResearchSettings
    from hermes.adapters.google.sheets_projection import DisabledSheetsProjection
    from hermes.application.affiliate_run_service import DisabledReviewDelivery

    captured = {}

    class CapturingRunService:
        def __init__(self, *args, **kwargs):
            captured["kwargs"] = kwargs

    monkeypatch.setattr(jobs, "AffiliateRunService", CapturingRunService)
    monkeypatch.setattr(repository_module, "SQLiteAffiliateResearchRepository", lambda _database: object())
    monkeypatch.setattr(database_module, "Database", lambda: object())
    monkeypatch.setattr(catalog_module, "AffiliateCatalogService", lambda _repository: object())
    monkeypatch.setattr(content_module, "AffiliateContentService", lambda *_args: object())
    monkeypatch.setattr(content_gateway_module, "AffiliateContentGateway", lambda _gateway: object())
    monkeypatch.setattr(llm_module, "HermesLLMGateway", lambda: object())
    monkeypatch.setattr(sheets_module.GoogleSheetsProjection, "from_environment", _external_tripwire)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_REVIEW_CHAT_ID", raising=False)

    settings = AffiliateResearchSettings(
        import_directory=tmp_path / "imports",
        google_sheets_enabled=False,
        google_sheets_credentials_file="",
        google_sheets_spreadsheet_id="",
        shortlist_limit=25,
        package_limit=10,
    )
    handler = jobs.build_affiliate_research_job_handler(settings=settings)

    assert isinstance(handler, jobs.AffiliateResearchJobHandler)
    assert isinstance(captured["kwargs"]["sheets_projection"], DisabledSheetsProjection)
    assert isinstance(captured["kwargs"]["review_delivery"], DisabledReviewDelivery)

    configured_projection = object()
    factory_repositories = []
    monkeypatch.setattr(
        sheets_module.GoogleSheetsProjection,
        "from_environment",
        lambda repository: factory_repositories.append(repository) or configured_projection,
    )
    enabled_handler = jobs.build_affiliate_research_job_handler(
        settings=AffiliateResearchSettings(
            import_directory=tmp_path / "imports",
            google_sheets_enabled=True,
            google_sheets_credentials_file="protected.json",
            google_sheets_spreadsheet_id="spreadsheet-id",
            shortlist_limit=25,
            package_limit=10,
        )
    )

    assert isinstance(enabled_handler, jobs.AffiliateResearchJobHandler)
    assert len(factory_repositories) == 1
    assert captured["kwargs"]["sheets_projection"] is configured_projection
