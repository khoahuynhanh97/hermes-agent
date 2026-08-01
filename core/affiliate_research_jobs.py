from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from hermes.adapters.affiliate.shopee_csv import ShopeeAffiliateCsvSource
from hermes.application.affiliate_run_service import AffiliateRunRequest, AffiliateRunService
from hermes.jobs import JobRepository


AFFILIATE_RESEARCH_JOB_TYPE = "affiliate_product_research"


class AffiliateResearchJobError(ValueError):
    """A permanent payload, authorization, or CSV import error."""


class AffiliateResearchJobHandler:
    """Validate a canonical queue payload before invoking the run service."""

    def __init__(
        self,
        import_directory: str | Path,
        run_service: AffiliateRunService,
        *,
        csv_validator: Callable[[Path, str], None] | None = None,
    ):
        self._import_directory = Path(import_directory).expanduser().resolve()
        self._run_service = run_service
        self._csv_validator = csv_validator or self._validate_csv

    def __call__(self, job: Mapping[str, Any]) -> dict[str, Any]:
        payload = job.get("payload")
        if not isinstance(payload, Mapping):
            raise AffiliateResearchJobError("affiliate job payload must be an object")
        owner_user_id = str(job.get("owner_user_id") or "").strip()
        if not owner_user_id:
            raise AffiliateResearchJobError("affiliate job owner_user_id is required")
        claimed_owner = payload.get("owner_user_id")
        if claimed_owner is not None and str(claimed_owner) != owner_user_id:
            raise AffiliateResearchJobError("affiliate job owner is not authorized")
        csv_path = self._csv_path(payload.get("csv_path"))
        try:
            self._csv_validator(csv_path, owner_user_id)
        except (OSError, UnicodeError, ValueError) as error:
            raise AffiliateResearchJobError(f"affiliate CSV is invalid: {error}") from error
        request = AffiliateRunRequest(
            owner_user_id=owner_user_id,
            idempotency_key=self._required_text(payload.get("idempotency_key"), "idempotency_key"),
            csv_path=str(csv_path),
            package_limit=self._package_limit(payload.get("package_limit", 10)),
            reference_urls=self._reference_urls(payload.get("reference_urls", ())),
        )
        result = self._run_service.run(request)
        return {
            "run_id": result.run_id,
            "package_ids": list(result.package_ids),
            "failed_projections": list(result.failed_projections),
        }

    def _csv_path(self, value: Any) -> Path:
        raw_path = self._required_text(value, "csv_path")
        candidate = Path(raw_path).expanduser().resolve()
        try:
            candidate.relative_to(self._import_directory)
        except ValueError as error:
            raise AffiliateResearchJobError("CSV path must stay inside the configured import directory") from error
        if candidate.suffix.lower() != ".csv":
            raise AffiliateResearchJobError("affiliate import must be a CSV file")
        if not candidate.is_file():
            raise AffiliateResearchJobError("affiliate CSV file was not found")
        return candidate

    @staticmethod
    def _validate_csv(path: Path, owner_user_id: str) -> None:
        ShopeeAffiliateCsvSource(path).load_batch(owner_user_id)

    @staticmethod
    def _required_text(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise AffiliateResearchJobError(f"affiliate job {name} is required")
        return value.strip()

    @staticmethod
    def _package_limit(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 5 <= value <= 10:
            raise AffiliateResearchJobError("affiliate job package_limit must be between 5 and 10")
        return value

    @staticmethod
    def _reference_urls(value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(url, str) or not url.strip() for url in value
        ):
            raise AffiliateResearchJobError("affiliate job reference_urls must be text values")
        return tuple(url.strip() for url in value)


class AffiliateResearchJobWorker:
    """Dedicated worker that never claims legacy jobs from the shared queue."""

    def __init__(self, jobs: JobRepository, handler: Callable[[Mapping[str, Any]], Mapping[str, Any]]):
        self._jobs = jobs
        self._handler = handler

    def process_next_job(self) -> bool:
        job = self._jobs.claim_next(AFFILIATE_RESEARCH_JOB_TYPE)
        if job is None:
            return False
        try:
            if self._jobs.is_cancel_requested(job["id"]):
                self._jobs.acknowledge_cancel(job["id"])
                return True
            result = self._handler(job)
            if self._jobs.is_cancel_requested(job["id"]):
                self._jobs.acknowledge_cancel(job["id"])
                return True
            run_id = str(result["run_id"])
            package_ids = tuple(result["package_ids"])
            failed_projections = tuple(result.get("failed_projections", ()))
            if failed_projections:
                self._jobs.fail(
                    job["id"],
                    f"Affiliate research projections pending: {', '.join(failed_projections)}",
                    retryable=True,
                )
                return True
            self._jobs.complete(
                job["id"],
                {
                    "run_id": run_id,
                    "package_ids": list(package_ids),
                    "summary": (
                        f"Affiliate research run {run_id} completed; "
                        f"{len(package_ids)} package(s) pending review."
                    ),
                },
            )
        except AffiliateResearchJobError as error:
            self._jobs.fail(job["id"], str(error), retryable=False)
        except Exception as error:
            self._jobs.fail(job["id"], str(error), retryable=True)
        return True


def build_affiliate_research_job_handler(
    import_directory: str | Path,
    *,
    run_service: AffiliateRunService | None = None,
) -> AffiliateResearchJobHandler:
    """Build the production composition without connecting to external projections."""
    if run_service is None:
        from hermes.adapters.model.affiliate_content_gateway import AffiliateContentGateway
        from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
        from hermes.application.affiliate_catalog_service import AffiliateCatalogService
        from hermes.application.affiliate_content_service import AffiliateContentService
        from hermes.db import Database
        from hermes.llm import HermesLLMGateway

        repository = SQLiteAffiliateResearchRepository(Database())
        run_service = AffiliateRunService(
            repository,
            AffiliateCatalogService(repository),
            AffiliateContentService(repository, AffiliateContentGateway(HermesLLMGateway())),
        )
    return AffiliateResearchJobHandler(import_directory, run_service)
