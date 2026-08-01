from __future__ import annotations

from pathlib import Path

import pytest

from hermes.db import Database
from hermes.jobs import JobRepository


def test_affiliate_worker_claims_only_affiliate_jobs_and_completes(tmp_path):
    from core.affiliate_research_jobs import AffiliateResearchJobWorker

    jobs = JobRepository(Database(tmp_path / "hermes.db"))
    jobs.enqueue("legacy", "42", "learning", {"source": "legacy"})
    jobs.enqueue("affiliate", "42", "affiliate_product_research", {"csv_path": "products.csv"})
    handled = []
    worker = AffiliateResearchJobWorker(
        jobs,
        handler=lambda job: handled.append(job) or {"run_id": "run-1", "package_ids": ["pkg-1"]},
    )

    assert worker.process_next_job() is True
    assert [job["id"] for job in handled] == ["affiliate"]
    assert jobs.get("affiliate")["state"] == "completed"
    assert jobs.get("affiliate")["result"]["summary"].startswith("Affiliate research run run-1")
    assert jobs.get("legacy")["state"] == "queued"


def test_affiliate_job_handler_rejects_csv_outside_configured_import_directory(tmp_path):
    from core.affiliate_research_jobs import AffiliateResearchJobError, AffiliateResearchJobHandler

    imports = tmp_path / "imports"
    imports.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("item_id\n1\n", encoding="utf-8")
    handler = AffiliateResearchJobHandler(imports, run_service=object())

    with pytest.raises(AffiliateResearchJobError, match="import directory"):
        handler({"id": "job-1", "owner_user_id": "42", "payload": {"csv_path": str(outside)}})


def test_affiliate_worker_marks_validation_errors_non_retryable(tmp_path):
    from core.affiliate_research_jobs import AffiliateResearchJobError, AffiliateResearchJobWorker

    jobs = JobRepository(Database(tmp_path / "hermes.db"))
    jobs.enqueue("affiliate", "42", "affiliate_product_research", {}, max_attempts=3)
    worker = AffiliateResearchJobWorker(
        jobs,
        handler=lambda _job: (_ for _ in ()).throw(AffiliateResearchJobError("bad payload")),
    )

    assert worker.process_next_job() is True
    assert jobs.get("affiliate")["state"] == "failed"
    assert jobs.get("affiliate")["attempts"] == 1
