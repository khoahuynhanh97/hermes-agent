from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Protocol, Sequence

from hermes.adapters.affiliate.shopee_csv import ShopeeAffiliateCsvSource
from hermes.domain.affiliate_research import ProjectionResult
from hermes.ports.affiliate_research import ReviewDelivery, SheetsProjection


@dataclass(frozen=True)
class AffiliateRunRequest:
    owner_user_id: str
    idempotency_key: str
    csv_path: str
    package_limit: int = 10
    reference_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunResult:
    run_id: str
    imported: int
    shortlisted: int
    package_ids: tuple[str, ...]
    reused: bool = False


class ProjectionFailureStore(Protocol):
    def record(
        self,
        projection: str,
        owner_user_id: str,
        run_id: str,
        result: ProjectionResult,
    ) -> None: ...


class ReferenceCollector(Protocol):
    def collect(
        self, owner_user_id: str, products: Sequence[Any], urls: Sequence[str]
    ) -> Sequence[Any]: ...


class DisabledSheetsProjection:
    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult:
        return ProjectionResult(ok=True, retryable=False, detail="disabled")


class DisabledReviewDelivery:
    def send_pending(self, owner_user_id: str, package_ids: Sequence[str]) -> ProjectionResult:
        return ProjectionResult(ok=True, retryable=False, detail="disabled")


class DisabledProjectionFailureStore:
    """Local default for deployments without the Task 7/8 retry stores."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, str, ProjectionResult]] = []

    def record(
        self,
        projection: str,
        owner_user_id: str,
        run_id: str,
        result: ProjectionResult,
    ) -> None:
        self.records.append((projection, owner_user_id, run_id, result))


class DisabledReferenceCollector:
    def collect(
        self, owner_user_id: str, products: Sequence[Any], urls: Sequence[str]
    ) -> Sequence[Any]:
        if urls:
            raise ValueError("reference collection is not configured")
        return ()


class AffiliateRunService:
    """Commit the affiliate research run before attempting external projections."""

    def __init__(
        self,
        repository: Any,
        catalog_service: Any,
        content_service: Any,
        *,
        source_factory: Callable[[str], Any] = ShopeeAffiliateCsvSource,
        sheets_projection: SheetsProjection | None = None,
        review_delivery: ReviewDelivery | None = None,
        projection_failures: ProjectionFailureStore | None = None,
        reference_collector: ReferenceCollector | None = None,
        snapshot_date: Callable[[], str] | None = None,
    ):
        self._repository = repository
        self._catalog = catalog_service
        self._content = content_service
        self._source_factory = source_factory
        self._sheets = sheets_projection or DisabledSheetsProjection()
        self._delivery = review_delivery or DisabledReviewDelivery()
        self._projection_failures = projection_failures or DisabledProjectionFailureStore()
        self._reference_collector = reference_collector or DisabledReferenceCollector()
        self._snapshot_date = snapshot_date or (lambda: date.today().isoformat())

    def run(self, request: AffiliateRunRequest) -> RunResult:
        self._validate_request(request)
        expected_run_id = self._run_id(request.owner_user_id, request.idempotency_key)
        run = self._repository.create_run(
            expected_run_id, request.owner_user_id, request.idempotency_key
        )
        run_id = str(run["id"])

        if run.get("status") == "completed":
            result = self._result_from_completed_run(request.owner_user_id, run_id, run)
            self._project(request.owner_user_id, result)
            return RunResult(
                run_id=result.run_id,
                imported=result.imported,
                shortlisted=result.shortlisted,
                package_ids=result.package_ids,
                reused=True,
            )

        imported = self._catalog.import_candidates(
            self._source_factory(request.csv_path),
            owner_user_id=request.owner_user_id,
            run_id=run_id,
            snapshot_date=self._snapshot_date(),
        )
        shortlisted = self._catalog.score_and_shortlist(
            owner_user_id=request.owner_user_id,
            run_id=run_id,
            minimum=15,
            maximum=25,
        )
        references = self._reference_collector.collect(
            request.owner_user_id, [item.product if hasattr(item, "product") else item for item in shortlisted], request.reference_urls
        )
        packages = self._content.create_packages(
            request.owner_user_id,
            run_id,
            [item.product if hasattr(item, "product") else item for item in shortlisted],
            references,
            per_run=request.package_limit,
        )
        result = RunResult(
            run_id=run_id,
            imported=int(imported.imported),
            shortlisted=len(shortlisted),
            package_ids=tuple(package.id for package in packages),
        )
        self._repository.finish_run(
            run_id,
            {
                "imported": result.imported,
                "shortlisted": result.shortlisted,
                "packaged": len(result.package_ids),
            },
        )
        self._project(request.owner_user_id, result)
        return result

    def _result_from_completed_run(self, owner_user_id: str, run_id: str, run: dict) -> RunResult:
        counters = run.get("counters") or {}
        packages = self._repository.list_packages(owner_user_id, run_id=run_id)
        return RunResult(
            run_id=run_id,
            imported=int(counters.get("imported", 0)),
            shortlisted=int(counters.get("shortlisted", 0)),
            package_ids=tuple(package.id for package in packages),
        )

    def _project(self, owner_user_id: str, result: RunResult) -> None:
        self._attempt_projection(
            "sheets", owner_user_id, result.run_id, lambda: self._sheets.sync(owner_user_id, result.run_id)
        )
        self._attempt_projection(
            "telegram",
            owner_user_id,
            result.run_id,
            lambda: self._delivery.send_pending(owner_user_id, result.package_ids),
        )

    def _attempt_projection(
        self,
        name: str,
        owner_user_id: str,
        run_id: str,
        invoke: Callable[[], ProjectionResult],
    ) -> None:
        try:
            outcome = invoke()
        except Exception as error:
            outcome = ProjectionResult(ok=False, retryable=True, detail=str(error)[:1000])
        if not outcome.ok:
            self._projection_failures.record(name, owner_user_id, run_id, outcome)

    @staticmethod
    def _run_id(owner_user_id: str, idempotency_key: str) -> str:
        value = f"{owner_user_id}\0{idempotency_key}".encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    @staticmethod
    def _validate_request(request: AffiliateRunRequest) -> None:
        if not request.owner_user_id.strip():
            raise ValueError("owner_user_id is required")
        if not request.idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not request.csv_path.strip():
            raise ValueError("csv_path is required")
        if isinstance(request.package_limit, bool) or not 5 <= request.package_limit <= 10:
            raise ValueError("package_limit must be between 5 and 10")
        if any(not isinstance(url, str) or not url.strip() for url in request.reference_urls):
            raise ValueError("reference_urls must contain non-empty strings")
