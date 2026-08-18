"""Run Tier-3 spec-compliant ``AffiliateAnalysis`` for the latest run.

Designed to be invoked manually after ``affiliate_research_worker.py``
finishes a run, or by an outer orchestrator. Idempotent: writes are
keyed on (owner, product, run, content_hash) so re-running yields
no duplicate rows.

Uses only the additive artifacts introduced for the spec:
* ``AffiliateAnalysisGateway`` (Hermes -> 9Router)
* ``SQLiteAffiliateAnalysisRepository`` (V7 schema)
* ``PublicWebUrlPolicy`` + ``SQLiteWebDocumentRepository`` for
  cached markdown lookup (graceful fallback if no references).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


from hermes.adapters.model.affiliate_analysis_gateway import AffiliateAnalysisGateway  # noqa: E402
from hermes.adapters.sqlite.affiliate_analysis_repository import (  # noqa: E402
    SQLiteAffiliateAnalysisRepository,
)
from hermes.application.affiliate_analysis_service import AffiliateAnalysisService  # noqa: E402
from hermes.db import Database  # noqa: E402
from hermes.llm import HermesLLMGateway  # noqa: E402


def build_service(database: Database | None = None) -> AffiliateAnalysisService:
    db = database or Database()
    repo = SQLiteAffiliateAnalysisRepository(db)
    gateway = AffiliateAnalysisGateway(HermesLLMGateway())
    return AffiliateAnalysisService(gateway, repo)


def run_for_owner(
    owner_user_id: str,
    run_id: str,
    *,
    limit: int = 25,
) -> list[str]:
    """Generate analyses for every shortlisted product in ``run_id``.

    Returns the analysis ids that were persisted or already existed.
    """

    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )
    from hermes.adapters.sqlite.web_document_repository import (
        SQLiteWebDocumentRepository,
    )

    db = Database()
    research_repo = SQLiteAffiliateResearchRepository(db)
    web_docs_repo = SQLiteWebDocumentRepository(db)
    
    products = research_repo.list_products(owner_user_id, run_id=run_id)
    shortlisted = [p for p in products if (p.score or 0) > 0][:limit]

    service = build_service(db)
    persisted: list[str] = []
    for product in shortlisted:
        references = research_repo.list_references(owner_user_id, product.id)
        web_docs = web_docs_repo.list_for_product(owner_user_id, run_id, product.id)
        
        analysis = service.analyze_product(
            owner_user_id=owner_user_id,
            run_id=run_id,
            product=product,
            references=references,
            web_documents=web_docs,
            fallback_used=not shortlisted or not references,
        )
        persisted.append(analysis.analysis_id)
    return persisted


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate spec-compliant AffiliateAnalysis rows for a run."
    )
    parser.add_argument("--owner", required=True, help="owner_user_id")
    parser.add_argument("--run", required=True, help="run_id from affiliate_research_worker")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(argv)

    analysis_ids = run_for_owner(args.owner, args.run, limit=args.limit)
    print(f"persisted_or_reused_analyses={len(analysis_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
