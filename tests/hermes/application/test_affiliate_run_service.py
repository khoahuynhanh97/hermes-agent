from __future__ import annotations

from dataclasses import dataclass

from hermes.domain.affiliate_research import ProjectionResult


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
