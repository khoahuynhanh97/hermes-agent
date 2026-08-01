from __future__ import annotations

from dataclasses import dataclass

import pytest

from hermes.db import Database
from hermes.domain.affiliate_research import ProductCandidate, ProjectionResult


@dataclass(frozen=True)
class _Package:
    id: str


class _Repository:
    def __init__(self):
        self.runs = {}
        self.packages = {}
        self.finish_calls = []

    def create_run(self, run_id, owner_user_id, idempotency_key):
        key = (owner_user_id, idempotency_key)
        if key not in self.runs:
            self.runs[key] = {"id": run_id, "status": "running", "counters": {}}
        return dict(self.runs[key])

    def finish_run(self, run_id, counters):
        self.finish_calls.append((run_id, dict(counters)))
        for run in self.runs.values():
            if run["id"] == run_id:
                run.update(status="completed", counters=dict(counters))
                return dict(run)
        raise LookupError(run_id)

    def list_packages(self, owner_user_id, run_id=None):
        return list(self.packages.get((owner_user_id, run_id), ()))

    def record_projection_failure(self, run_id, projection, detail, retryable):
        for run in self.runs.values():
            if run["id"] == run_id:
                failures = run["counters"].setdefault("projection_failures", {})
                failures[projection] = {"detail": detail, "retryable": retryable}
                return dict(run)
        raise LookupError(run_id)

    def clear_projection_failure(self, run_id, projection):
        for run in self.runs.values():
            if run["id"] == run_id:
                run["counters"].get("projection_failures", {}).pop(projection, None)
                return dict(run)
        raise LookupError(run_id)


class _Catalog:
    def __init__(self):
        self.import_calls = []
        self.shortlist_calls = []

    def import_candidates(self, source, *, owner_user_id, run_id, snapshot_date):
        self.import_calls.append((source, owner_user_id, run_id, snapshot_date))
        return type("ImportSummary", (), {"imported": 2, "rejected": 0, "errors": 0})()

    def score_and_shortlist(self, *, owner_user_id, run_id, minimum, maximum):
        self.shortlist_calls.append((owner_user_id, run_id, minimum, maximum))
        return ["product-1", "product-2"]


class _Content:
    def __init__(self, repository):
        self.repository = repository
        self.calls = []

    def create_packages(self, owner_user_id, run_id, products, references, *, per_run):
        self.calls.append((owner_user_id, run_id, tuple(products), tuple(references), per_run))
        packages = [_Package("package-1"), _Package("package-2")]
        self.repository.packages[(owner_user_id, run_id)] = packages
        return packages


class _ProjectionFailures:
    def __init__(self):
        self.records = []

    def record(self, projection, owner_user_id, run_id, result):
        self.records.append((projection, owner_user_id, run_id, result))


class _FailingSheets:
    def __init__(self):
        self.calls = []

    def sync(self, owner_user_id, run_id):
        self.calls.append((owner_user_id, run_id))
        return ProjectionResult(ok=False, retryable=True, detail="temporarily unavailable")


class _Delivery:
    def __init__(self):
        self.calls = []

    def send_pending(self, owner_user_id, package_ids):
        self.calls.append((owner_user_id, tuple(package_ids)))
        return ProjectionResult(ok=True, retryable=False, detail="sent")


class _SuccessfulSheets:
    def __init__(self):
        self.calls = []

    def sync(self, owner_user_id, run_id):
        self.calls.append((owner_user_id, run_id))
        return ProjectionResult(ok=True, retryable=False, detail="synced")


class _NonRetryableSheets:
    def __init__(self):
        self.calls = []

    def sync(self, owner_user_id, run_id):
        self.calls.append((owner_user_id, run_id))
        return ProjectionResult(ok=False, retryable=False, detail="credentials rejected")


class _NeverCalledSheets:
    def sync(self, *args, **kwargs):
        raise AssertionError("non-retryable projection must not be called again")


class _FailOnceContent(_Content):
    def __init__(self, repository):
        super().__init__(repository)
        self.failures_remaining = 1

    def create_packages(self, *args, **kwargs):
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("content gateway unavailable")
        return super().create_packages(*args, **kwargs)


class _NeverCalledCatalog:
    def import_candidates(self, *args, **kwargs):
        raise AssertionError("completed run must not import again")

    def score_and_shortlist(self, *args, **kwargs):
        raise AssertionError("completed run must not shortlist again")


class _NeverCalledContent:
    def create_packages(self, *args, **kwargs):
        raise AssertionError("completed run must not create packages again")


class _EmptyContent:
    def __init__(self):
        self.calls = []

    def create_packages(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return []


class _FailOnceEmptyContent(_EmptyContent):
    def __init__(self):
        super().__init__()
        self.failures_remaining = 1

    def create_packages(self, *args, **kwargs):
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("package persistence interrupted")
        return super().create_packages(*args, **kwargs)


class _OneCandidateSource:
    def load(self, owner_user_id):
        return [
            ProductCandidate(
                owner_user_id=owner_user_id,
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
                visual_signals=("light",),
                source_type="affiliate_csv",
                source_url="authorized_csv:products.csv",
                authorization_scope="user_export",
                rights_status="authorized_affiliate_export",
                content_hash="candidate-101",
            )
        ]


def test_same_idempotency_key_returns_existing_run_and_retries_projection():
    from hermes.application.affiliate_run_service import AffiliateRunRequest, AffiliateRunService

    repository = _Repository()
    catalog = _Catalog()
    content = _Content(repository)
    sheets = _FailingSheets()
    delivery = _Delivery()
    failures = _ProjectionFailures()
    service = AffiliateRunService(
        repository,
        catalog,
        content,
        source_factory=lambda path: {"csv": path},
        sheets_projection=sheets,
        review_delivery=delivery,
        projection_failures=failures,
        snapshot_date=lambda: "2026-08-01",
    )
    request = AffiliateRunRequest("42", "run-key-1", "products.csv", package_limit=5)

    first = service.run(request)
    second = service.run(request)

    assert first.run_id == second.run_id
    assert first.package_ids == ("package-1", "package-2")
    assert second.reused is True
    assert len(catalog.import_calls) == 1
    assert len(content.calls) == 1
    assert len(repository.finish_calls) == 1
    assert len(sheets.calls) == 2
    assert len(failures.records) == 2
    assert repository.list_packages("42", first.run_id) == [_Package("package-1"), _Package("package-2")]


def test_configured_shortlist_limit_controls_scoring_maximum():
    from hermes.application.affiliate_run_service import AffiliateRunRequest, AffiliateRunService

    repository = _Repository()
    catalog = _Catalog()
    service = AffiliateRunService(
        repository,
        catalog,
        _Content(repository),
        source_factory=lambda path: {"csv": path},
        shortlist_limit=15,
    )

    service.run(AffiliateRunRequest("42", "run-key-shortlist-15", "products.csv", package_limit=5))

    assert catalog.shortlist_calls[0][2:] == (15, 15)


def test_package_failure_leaves_run_running_and_retry_is_not_reused():
    from hermes.application.affiliate_run_service import AffiliateRunRequest, AffiliateRunService

    repository = _Repository()
    catalog = _Catalog()
    content = _FailOnceContent(repository)
    service = AffiliateRunService(
        repository,
        catalog,
        content,
        source_factory=lambda path: {"csv": path},
        snapshot_date=lambda: "2026-08-01",
    )
    request = AffiliateRunRequest("42", "run-key-2", "products.csv", package_limit=5)

    with pytest.raises(RuntimeError, match="content gateway"):
        service.run(request)

    assert next(iter(repository.runs.values()))["status"] == "running"
    recovered = service.run(request)

    assert recovered.reused is False
    assert len(catalog.import_calls) == 2
    assert len(content.calls) == 1
    assert len(repository.finish_calls) == 1


def test_real_catalog_keeps_incomplete_run_running_until_package_persistence_recovers(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
    from hermes.application.affiliate_catalog_service import AffiliateCatalogService
    from hermes.application.affiliate_run_service import AffiliateRunRequest, AffiliateRunService

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    content = _FailOnceEmptyContent()
    service = AffiliateRunService(
        repository,
        AffiliateCatalogService(repository),
        content,
        source_factory=lambda _path: _OneCandidateSource(),
        snapshot_date=lambda: "2026-08-01",
    )
    request = AffiliateRunRequest("42", "run-key-real", "products.csv", package_limit=5)
    run_id = AffiliateRunService._run_id(request.owner_user_id, request.idempotency_key)

    with pytest.raises(RuntimeError, match="package persistence"):
        service.run(request)

    assert repository.create_run(run_id, "42", "run-key-real")["status"] == "running"
    recovered = service.run(request)

    assert recovered.reused is False
    assert repository.create_run(run_id, "42", "run-key-real")["status"] == "completed"


def test_completed_run_retries_durable_projection_with_fresh_service_instance(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
    from hermes.application.affiliate_run_service import AffiliateRunRequest, AffiliateRunService

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    request = AffiliateRunRequest("42", "run-key-3", "products.csv", package_limit=5)
    run_id = AffiliateRunService._run_id(request.owner_user_id, request.idempotency_key)

    failing = _FailingSheets()
    content = _EmptyContent()
    first_service = AffiliateRunService(
        repository,
        _Catalog(),
        content,
        source_factory=lambda path: {"csv": path},
        sheets_projection=failing,
    )
    first = first_service.run(request)

    assert first.reused is False
    assert first.failed_projections == ("sheets",)
    assert repository.create_run(run_id, "42", "run-key-3")["counters"]["projection_failures"] == {
        "sheets": {"detail": "temporarily unavailable", "retryable": True}
    }

    succeeding = _SuccessfulSheets()
    second_service = AffiliateRunService(
        repository,
        _NeverCalledCatalog(),
        _NeverCalledContent(),
        sheets_projection=succeeding,
    )
    second = second_service.run(request)

    assert second.reused is True
    assert second.failed_projections == ()
    assert succeeding.calls == [("42", run_id)]
    assert "projection_failures" not in repository.create_run(run_id, "42", "run-key-3")["counters"]


def test_completed_run_keeps_nonretryable_projection_failure_without_reattempting(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
    from hermes.application.affiliate_run_service import AffiliateRunRequest, AffiliateRunService

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    request = AffiliateRunRequest("42", "run-key-4", "products.csv", package_limit=5)
    first_service = AffiliateRunService(
        repository,
        _Catalog(),
        _EmptyContent(),
        source_factory=lambda path: {"csv": path},
        sheets_projection=_NonRetryableSheets(),
    )

    first = first_service.run(request)
    run_id = AffiliateRunService._run_id(request.owner_user_id, request.idempotency_key)
    second = AffiliateRunService(
        repository,
        _NeverCalledCatalog(),
        _NeverCalledContent(),
        sheets_projection=_NeverCalledSheets(),
    ).run(request)

    assert first.retryable_projection_failures == ()
    assert first.nonretryable_projection_failures == ("sheets",)
    assert repository.create_run(run_id, "42", "run-key-4")["counters"]["projection_failures"] == {
        "sheets": {"detail": "credentials rejected", "retryable": False}
    }
    assert second.reused is True
    assert second.retryable_projection_failures == ()
    assert second.nonretryable_projection_failures == ("sheets",)


def test_completed_outbox_replays_after_crash_before_any_projection(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )
    from hermes.application.affiliate_run_service import AffiliateRunRequest, AffiliateRunService

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    request = AffiliateRunRequest("42", "crash-before-projection", "products.csv", package_limit=5)
    run_id = AffiliateRunService._run_id(request.owner_user_id, request.idempotency_key)
    repository.create_run(run_id, "42", request.idempotency_key)
    repository.complete_run(
        run_id,
        {"imported": 0, "updated": 0, "rejected": 0, "errors": 0, "shortlisted": 0, "packaged": 0},
        ("sheets", "telegram"),
    )
    sheets = _SuccessfulSheets()
    delivery = _Delivery()

    result = AffiliateRunService(
        SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db")),
        _NeverCalledCatalog(),
        _NeverCalledContent(),
        sheets_projection=sheets,
        review_delivery=delivery,
    ).run(request)

    assert result.reused is True
    assert result.failed_projections == ()
    assert sheets.calls == [("42", run_id)]
    assert delivery.calls == [("42", ())]
