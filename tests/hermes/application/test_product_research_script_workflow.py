from __future__ import annotations

import csv
from dataclasses import dataclass

from hermes.domain.affiliate_research import ProductCandidate, ProjectionResult


def candidate(number: int) -> ProductCandidate:
    return ProductCandidate(
        owner_user_id="42",
        platform="shopee",
        external_product_id=str(number),
        name=f"Keyboard {number}",
        category="keyboard",
        price_vnd=350000,
        sold_count=1000 + number,
        rating=4.8,
        review_count=100,
        commission_rate=None,
        shop_name="Shop",
        product_url=f"https://example.test/{number}",
        image_urls=(f"https://example.test/{number}.jpg",),
        visual_signals=("tactile_interaction", "visible_problem_solution"),
        source_type="fake_crawler",
        source_url=f"https://example.test/{number}",
        authorization_scope="public_scrape",
        rights_status="reference_only",
        content_hash=f"hash-{number}",
    )


class FakeSource:
    def __init__(self, rows):
        self.rows = rows

    def load(self, owner_user_id: str):
        return self.rows


@dataclass
class FakeSelection:
    status: str
    rows: list[ProductCandidate]
    warnings: tuple[str, ...] = ()

    def load(self, owner_user_id: str):
        return self.rows


class FakeSelector:
    def __init__(self, selection):
        self.selection = selection

    def select(self, intent):
        return self.selection


class FakeSheets:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def sync(self, owner_user_id, run_id):
        self.calls.append((owner_user_id, run_id))
        return self.result


class FakeGateway:
    def __init__(self, fail=False):
        self.fail = fail

    def generate(self, product, references):
        if self.fail:
            raise RuntimeError("model offline")
        seed = product.external_product_id
        return {
            "audience": f"shopper-{seed}",
            "angle": f"angle-{seed}",
            "angle_reason": f"reason-{seed}",
            "hook": f"hook-{seed}",
            "script": f"script-{seed}",
            "duration_seconds": 45,
            "storyboard": [{"visual": f"scene-{seed}", "start": 0, "end": 45}],
            "ai_prompts": [f"prompt-{seed}"],
            "voiceover_plan": f"voiceover-{seed}",
            "text_overlays": [f"overlay-{seed}"],
            "claims": [{"text": f"claim-{seed}", "evidence_url": product.product_url}],
            "warnings": ["Verify price and commission before publishing."],
        }


def intent():
    from hermes.application.product_research_intent import ProductResearchIntent

    return ProductResearchIntent.from_message("42", "crawl ngành bàn phím, giá 200k-500k")


def build_workflow(tmp_path, selection, gateway=None, sheets=None):
    from hermes.adapters.local.sheet_projection import LocalSheetProjection
    from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
    from hermes.application.affiliate_catalog_service import AffiliateCatalogService
    from hermes.application.affiliate_content_service import AffiliateContentService
    from hermes.application.product_research_script_workflow import ProductResearchScriptWorkflow
    from hermes.db import Database

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    return ProductResearchScriptWorkflow(
        repository=repository,
        catalog_service=AffiliateCatalogService(repository),
        content_service=AffiliateContentService(repository, gateway or FakeGateway()),
        source_selector=FakeSelector(selection),
        local_projection=LocalSheetProjection(repository, tmp_path / "exports"),
        google_projection=sheets,
        snapshot_date=lambda: "2026-08-04",
    )


def test_workflow_exports_local_sheets_and_generates_short_scripts(tmp_path):
    workflow = build_workflow(tmp_path, FakeSelection("crawler", [candidate(i) for i in range(1, 31)]))

    result = workflow.run(intent())

    assert result.status == "completed"
    assert result.imported == 30
    assert result.shortlisted >= 15
    assert result.package_ids
    assert "Products" in result.local_sheet_paths
    with open(result.local_sheet_paths["Scripts"], encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows


def test_workflow_returns_csv_fallback_when_crawler_disabled(tmp_path):
    workflow = build_workflow(
        tmp_path,
        FakeSelection("needs_csv_feed", [], ("Marketplace crawler is disabled; provide CSV/feed fallback.",)),
    )

    result = workflow.run(intent())

    assert result.status == "needs_csv_feed"
    assert result.imported == 0
    assert "provide CSV/feed" in result.warnings[0]


def test_workflow_keeps_local_output_when_google_sheets_fails(tmp_path):
    sheets = FakeSheets(ProjectionResult(ok=False, retryable=True, detail="offline"))
    workflow = build_workflow(
        tmp_path,
        FakeSelection("crawler", [candidate(i) for i in range(1, 31)]),
        sheets=sheets,
    )

    result = workflow.run(intent())

    assert result.status == "completed_with_projection_warnings"
    assert result.retryable_projection_failures == ("google_sheets",)
    assert result.local_sheet_paths["Products"].endswith("Products.csv")


def test_workflow_marks_script_generation_pending_when_model_unavailable(tmp_path):
    workflow = build_workflow(
        tmp_path,
        FakeSelection("crawler", [candidate(i) for i in range(1, 31)]),
        gateway=FakeGateway(fail=True),
    )

    result = workflow.run(intent())

    assert result.status == "completed_with_script_warnings"
    assert result.package_ids == ()
    assert any("script generation" in warning for warning in result.warnings)