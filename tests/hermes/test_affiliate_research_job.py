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


def test_production_csv_validation_enforces_100_to_200_valid_candidates(tmp_path):
    from core.affiliate_research_jobs import AffiliateResearchJobHandler

    path = tmp_path / "products.csv"
    rows = ["item_id,product_name,category,price,product_link"]
    rows.extend(
        f"{index},Mouse {index},mouse,300000,https://example.test/{index}"
        for index in range(99)
    )
    path.write_text("\n".join(rows), encoding="utf-8")

    with pytest.raises(ValueError, match="100 and 200"):
        AffiliateResearchJobHandler._validate_csv(path, "42")


def test_handler_classifies_invalid_reference_as_permanent_job_error(tmp_path):
    from core.affiliate_research_jobs import (
        AffiliateResearchJobError,
        AffiliateResearchJobHandler,
    )
    from hermes.application.affiliate_reference_service import PermanentReferenceError

    path = tmp_path / "products.csv"
    path.write_text("header\n", encoding="utf-8")

    class RunService:
        def run(self, _request):
            raise PermanentReferenceError("unauthorized TikTok URL")

    handler = AffiliateResearchJobHandler(
        tmp_path,
        RunService(),
        csv_validator=lambda *_args: None,
        default_package_limit=5,
    )

    with pytest.raises(AffiliateResearchJobError, match="unauthorized"):
        handler(
            {
                "owner_user_id": "42",
                "payload": {
                    "csv_path": str(path),
                    "idempotency_key": "key-1",
                    "package_limit": 5,
                    "reference_urls": [
                        "https://www.tiktok.com/@creator/video/123"
                    ],
                },
            }
        )


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


def test_affiliate_worker_requeues_when_projections_are_pending(tmp_path):
    from core.affiliate_research_jobs import AffiliateResearchJobWorker

    jobs = JobRepository(Database(tmp_path / "hermes.db"))
    jobs.enqueue("affiliate", "42", "affiliate_product_research", {}, max_attempts=2)
    worker = AffiliateResearchJobWorker(
        jobs,
        handler=lambda _job: {
            "run_id": "run-1",
            "package_ids": ["pkg-1"],
            "failed_projections": ["sheets"],
        },
    )

    assert worker.process_next_job() is True
    assert jobs.get("affiliate")["state"] == "queued"
    assert jobs.get("affiliate")["attempts"] == 1


def test_affiliate_worker_fails_without_requeue_for_nonretryable_projections(tmp_path):
    from core.affiliate_research_jobs import AffiliateResearchJobWorker

    jobs = JobRepository(Database(tmp_path / "hermes.db"))
    jobs.enqueue("affiliate", "42", "affiliate_product_research", {}, max_attempts=2)
    worker = AffiliateResearchJobWorker(
        jobs,
        handler=lambda _job: {
            "run_id": "run-1",
            "package_ids": ["pkg-1"],
            "retryable_projection_failures": [],
            "nonretryable_projection_failures": ["sheets"],
        },
    )

    assert worker.process_next_job() is True
    assert jobs.get("affiliate")["state"] == "failed"
    assert jobs.get("affiliate")["attempts"] == 1


def test_affiliate_worker_acknowledges_cancellation_before_handler(tmp_path):
    from core.affiliate_research_jobs import AffiliateResearchJobWorker

    jobs = JobRepository(Database(tmp_path / "hermes.db"))
    jobs.enqueue("affiliate", "42", "affiliate_product_research", {})
    original_claim = jobs.claim_next

    def claim_and_cancel(job_type):
        job = original_claim(job_type)
        jobs.cancel(job["id"], "42")
        return job

    jobs.claim_next = claim_and_cancel
    worker = AffiliateResearchJobWorker(
        jobs,
        handler=lambda _job: (_ for _ in ()).throw(AssertionError("handler must not run")),
    )

    assert worker.process_next_job() is True
    assert jobs.get("affiliate")["state"] == "cancelled"


def test_affiliate_worker_acknowledges_cancellation_after_handler(tmp_path):
    from core.affiliate_research_jobs import AffiliateResearchJobWorker

    jobs = JobRepository(Database(tmp_path / "hermes.db"))
    jobs.enqueue("affiliate", "42", "affiliate_product_research", {})

    def handle(job):
        jobs.cancel(job["id"], "42")
        return {"run_id": "run-1", "package_ids": ["pkg-1"]}

    assert AffiliateResearchJobWorker(jobs, handle).process_next_job() is True
    assert jobs.get("affiliate")["state"] == "cancelled"
    assert jobs.get("affiliate")["result"] == {}


def test_production_worker_entry_point_starts_in_once_mode(monkeypatch):
    from scripts import affiliate_research_worker

    calls = []
    worker = type(
        "Worker",
        (),
        {"process_next_job": lambda self: calls.append("processed") or False},
    )()
    monkeypatch.setattr(affiliate_research_worker, "build_worker", lambda: worker)

    assert affiliate_research_worker.main(["--once"]) == 0
    assert calls == ["processed"]


def test_production_worker_startup_recovers_interrupted_jobs(monkeypatch):
    from scripts import affiliate_research_worker

    calls = []

    class Jobs:
        def recover_interrupted(self):
            calls.append("recovered")

    jobs = Jobs()
    handler = object()
    monkeypatch.setattr(affiliate_research_worker, "JobRepository", lambda: jobs)
    monkeypatch.setattr(
        affiliate_research_worker,
        "build_affiliate_research_job_handler",
        lambda: handler,
    )

    worker = affiliate_research_worker.build_worker()

    assert calls == ["recovered"]
    assert worker._jobs is jobs
    assert worker._handler is handler
