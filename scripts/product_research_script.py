from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_workflow():
    from hermes.adapters.google.sheets_projection import DisabledSheetsProjection, GoogleSheetsProjection
    from hermes.adapters.local.sheet_projection import LocalSheetProjection
    from hermes.adapters.model.affiliate_content_gateway import AffiliateContentGateway
    from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
    from hermes.affiliate_config import load_affiliate_research_settings
    from hermes.application.affiliate_catalog_service import AffiliateCatalogService
    from hermes.application.affiliate_content_service import AffiliateContentService
    from hermes.application.product_research_script_workflow import ProductResearchScriptWorkflow
    from hermes.application.product_source_selector import ProductSourceSelector
    from hermes.db import Database

    settings = load_affiliate_research_settings()
    repository = SQLiteAffiliateResearchRepository(Database())
    google_projection = (
        GoogleSheetsProjection.from_environment(repository)
        if settings.google_sheets_enabled
        else DisabledSheetsProjection()
    )
    return ProductResearchScriptWorkflow(
        repository=repository,
        catalog_service=AffiliateCatalogService(repository),
        content_service=AffiliateContentService(repository, AffiliateContentGateway()),
        source_selector=ProductSourceSelector(settings),
        local_projection=LocalSheetProjection(repository, settings.local_sheet_output_dir),
        google_projection=google_projection,
        shortlist_limit=settings.shortlist_limit,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Hermes product research sheet + script workflow")
    parser.add_argument("--owner", required=True, help="Owner user id")
    parser.add_argument("--message", required=True, help="Natural product research request")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from hermes.application.product_research_intent import ProductResearchIntent

    intent = ProductResearchIntent.from_message(args.owner, args.message)
    result = build_workflow().run(intent)
    print(result.to_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())