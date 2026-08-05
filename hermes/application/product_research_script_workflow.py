from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from hermes.application.affiliate_run_service import DisabledSheetsProjection
from hermes.application.product_research_intent import ProductResearchIntent
from hermes.domain.affiliate_research import ProjectionResult


@dataclass(frozen=True)
class ProductResearchScriptResult:
    run_id: str
    status: str
    imported: int
    shortlisted: int
    package_ids: tuple[str, ...]
    local_sheet_paths: dict[str, str]
    warnings: tuple[str, ...] = ()
    retryable_projection_failures: tuple[str, ...] = ()
    nonretryable_projection_failures: tuple[str, ...] = ()

    def to_report(self) -> str:
        lines = [
            "# Product Research Script Run",
            "",
            f"Run ID: {self.run_id}",
            f"Status: {self.status}",
            f"Imported: {self.imported}",
            f"Shortlisted: {self.shortlisted}",
            f"Scripts: {len(self.package_ids)}",
            "",
            "## Local Sheets",
        ]
        for name, path in sorted(self.local_sheet_paths.items()):
            lines.append(f"- {name}: `{path}`")
        if self.warnings:
            lines.extend(["", "## Warnings"])
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines) + "\n"


class ProductResearchScriptWorkflow:
    def __init__(
        self,
        *,
        repository: Any,
        catalog_service: Any,
        content_service: Any,
        source_selector: Any,
        local_projection: Any,
        google_projection: Any | None = None,
        snapshot_date: Callable[[], str] | None = None,
        shortlist_limit: int = 25,
    ):
        self._repository = repository
        self._catalog = catalog_service
        self._content = content_service
        self._source_selector = source_selector
        self._local_projection = local_projection
        self._google_projection = google_projection or DisabledSheetsProjection()
        self._snapshot_date = snapshot_date or (lambda: date.today().isoformat())
        self._shortlist_limit = shortlist_limit

    def run(self, intent: ProductResearchIntent) -> ProductResearchScriptResult:
        run_id = _run_id(intent.owner_user_id, intent.idempotency_key)
        warnings: list[str] = []
        selection = self._source_selector.select(intent)
        products = selection.load(intent.owner_user_id)
        warnings.extend(selection.warnings)
        if not products:
            return ProductResearchScriptResult(
                run_id=run_id,
                status="needs_csv_feed",
                imported=0,
                shortlisted=0,
                package_ids=(),
                local_sheet_paths={},
                warnings=tuple(warnings or ["No products were collected; provide CSV/feed fallback."]),
            )

        self._repository.create_run(run_id, intent.owner_user_id, intent.idempotency_key)
        imported = self._catalog.import_candidates(
            _ListProductSource(products),
            owner_user_id=intent.owner_user_id,
            run_id=run_id,
            snapshot_date=self._snapshot_date(),
        )
        shortlisted = self._catalog.score_and_shortlist(
            owner_user_id=intent.owner_user_id,
            run_id=run_id,
            minimum=15,
            maximum=self._shortlist_limit,
        )
        package_ids: tuple[str, ...] = ()
        script_failed = False
        try:
            packages = self._content.create_packages(
                intent.owner_user_id,
                run_id,
                [item.product if hasattr(item, "product") else item for item in shortlisted],
                (),
                per_run=intent.script_limit,
            )
            package_ids = tuple(package.id for package in packages)
        except Exception as error:
            script_failed = True
            warnings.append(f"script generation pending: {str(error)[:200]}")

        counters = {
            "imported": int(imported.imported),
            "updated": int(getattr(imported, "updated", 0)),
            "rejected": int(getattr(imported, "rejected", 0)),
            "errors": int(getattr(imported, "errors", 0)),
            "shortlisted": len(shortlisted),
            "packaged": len(package_ids),
        }
        complete_run = getattr(self._repository, "complete_run", None)
        if complete_run is None:
            self._repository.finish_run(run_id, counters)
        else:
            complete_run(run_id, counters, ("local_sheets", "google_sheets"), projection_items={})

        local_result = self._local_projection.sync(intent.owner_user_id, run_id)
        if not local_result.ok:
            warnings.append(f"local sheet export failed: {local_result.detail}")
        google_result = self._google_projection.sync(intent.owner_user_id, run_id)
        retryable, nonretryable = _projection_failures("google_sheets", google_result)
        status = "completed"
        if script_failed:
            status = "completed_with_script_warnings"
        elif retryable or nonretryable or not local_result.ok:
            status = "completed_with_projection_warnings"
        return ProductResearchScriptResult(
            run_id=run_id,
            status=status,
            imported=int(imported.imported),
            shortlisted=len(shortlisted),
            package_ids=package_ids,
            local_sheet_paths=self._local_projection.output_paths(intent.owner_user_id, run_id),
            warnings=tuple(warnings),
            retryable_projection_failures=retryable,
            nonretryable_projection_failures=nonretryable,
        )


class _ListProductSource:
    def __init__(self, products):
        self._products = list(products)

    def load(self, owner_user_id: str):
        return list(self._products)


def _run_id(owner_user_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{owner_user_id}\0{idempotency_key}".encode("utf-8")).hexdigest()
    return f"affiliate_run_{digest[:24]}"


def _projection_failures(name: str, result: ProjectionResult):
    if result.ok:
        return (), ()
    return ((name,), ()) if result.retryable else ((), (name,))