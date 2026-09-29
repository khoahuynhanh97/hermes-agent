"""Unified ProductVideoCoordinator for Scheduler, CLI, and REST entry points."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from hermes_personal.application.operator_handler import approve_and_advance_workflow
from hermes_personal.product_video.handlers import (
    ProductVideoWorkflowState,
    start_product_video_workflow,
)
from hermes_personal.workflows.repository import WorkflowRepository
from hermes_personal.workflows.worker import run_worker

from .contracts import (
    BatchStartResult,
    CandidateItem,
    ExchangeProduct,
    SkippedProduct,
    StartedProduct,
)
from .importer import (
    DEFAULT_EXCHANGE_INBOX,
    ExchangeImporter,
)
from .repository import DailyImportRepository


class ProductVideoCoordinator:
    """The single coordinator for Daily Product Selection, workflow starting, and approvals.

    All entry points (Windows Task Scheduler, CLI commands, and REST endpoints)
    must call through this coordinator to ensure identical business logic,
    strict idempotency, and atomic claim protection.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        inbox_root: Path | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.connection = connection
        self.importer = ExchangeImporter(inbox_root)
        self.import_repo = DailyImportRepository(connection)
        self.workflow_repo = WorkflowRepository(connection)
        self.db_path = db_path

    def list_candidates(
        self,
        target_date: date | None = None,
        status_filter: str | None = None,
    ) -> list[CandidateItem]:
        """Read model: lists all candidate products from the latest exchange manifest."""
        batch_dir = self.importer.find_latest_ready_batch(target_date)
        manifest = self.importer.load_manifest(batch_dir)

        ledger_by_key = self.import_repo.get_all_for_date(manifest.production_date)
        ledger_by_canon = self.import_repo.get_all_active_by_canonical_key()
        candidates: list[CandidateItem] = []

        for p in manifest.products:
            is_valid, rejection_reason, valid_imgs = self.importer.validate_admission(p, batch_dir)

            enriched_imgs = []
            for v_img in valid_imgs:
                item = dict(v_img)
                rel = item.get("relative_path")
                if rel:
                    item["asset_url"] = f"/api/personal/product-video/assets/{manifest.production_date}/{manifest.batch_id}/{rel}"
                enriched_imgs.append(item)

            if not is_valid:
                invalid_imgs = []
                for img in p.images:
                    item = img.to_dict()
                    if img.relative_path:
                        item["asset_url"] = f"/api/personal/product-video/assets/{manifest.production_date}/{manifest.batch_id}/{img.relative_path}"
                    invalid_imgs.append(item)

                candidates.append(
                    CandidateItem(
                        priority=p.priority,
                        source_date=manifest.production_date,
                        source_batch_id=manifest.batch_id,
                        source_product_id=p.source_product_id,
                        canonical_product_key=p.canonical_product_key,
                        product_key=p.product_key,
                        name=p.name,
                        brand=p.brand,
                        model=p.model,
                        variant=p.variant,
                        price_display=p.price_display,
                        price_min=p.price_min,
                        price_max=p.price_max,
                        hot_reason=p.hot_reason,
                        key_features=p.key_features,
                        keywords=p.keywords,
                        images=invalid_imgs,
                        status="invalid",
                        internal_state="invalid",
                        rejection_reason=rejection_reason,
                    )
                )
                continue

            ledger_entry = ledger_by_key.get(p.product_key) or ledger_by_canon.get(p.canonical_product_key)
            if ledger_entry is None:
                candidates.append(
                    CandidateItem(
                        priority=p.priority,
                        source_date=manifest.production_date,
                        source_batch_id=manifest.batch_id,
                        source_product_id=p.source_product_id,
                        canonical_product_key=p.canonical_product_key,
                        product_key=p.product_key,
                        name=p.name,
                        brand=p.brand,
                        model=p.model,
                        variant=p.variant,
                        price_display=p.price_display,
                        price_min=p.price_min,
                        price_max=p.price_max,
                        hot_reason=p.hot_reason,
                        key_features=p.key_features,
                        keywords=p.keywords,
                        images=enriched_imgs,
                        status="unprocessed",
                        internal_state="imported",
                    )
                )
                continue

            int_status = ledger_entry["status"]
            wf_id = ledger_entry["workflow_id"]
            wf_data = self.workflow_repo.get_workflow(wf_id)

            if wf_data is None:
                candidates.append(
                    CandidateItem(
                        priority=p.priority,
                        source_date=manifest.production_date,
                        source_batch_id=manifest.batch_id,
                        source_product_id=p.source_product_id,
                        canonical_product_key=p.canonical_product_key,
                        product_key=p.product_key,
                        name=p.name,
                        brand=p.brand,
                        model=p.model,
                        variant=p.variant,
                        price_display=p.price_display,
                        price_min=p.price_min,
                        price_max=p.price_max,
                        hot_reason=p.hot_reason,
                        key_features=p.key_features,
                        keywords=p.keywords,
                        images=enriched_imgs,
                        status="unprocessed" if int_status != "error" else "invalid",
                        internal_state=int_status,
                        rejection_reason=ledger_entry.get("last_error"),
                    )
                )
                continue

            agg, _version = wf_data
            wf_state = str(agg.get("state") or "")
            approval_id = agg.get("pending_approval_id")
            gate = agg.get("pending_approval_gate")

            if wf_state == ProductVideoWorkflowState.COMPLETED.value:
                ui_status = "completed"
            elif wf_state == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value:
                ui_status = "awaiting_product_lock"
            else:
                ui_status = "in_production"

            candidates.append(
                CandidateItem(
                    priority=p.priority,
                    source_date=manifest.production_date,
                    source_batch_id=manifest.batch_id,
                    source_product_id=p.source_product_id,
                    canonical_product_key=p.canonical_product_key,
                    product_key=p.product_key,
                    name=p.name,
                    brand=p.brand,
                    model=p.model,
                    variant=p.variant,
                    price_display=p.price_display,
                    price_min=p.price_min,
                    price_max=p.price_max,
                    hot_reason=p.hot_reason,
                    key_features=p.key_features,
                    keywords=p.keywords,
                    images=enriched_imgs,
                    status=ui_status,
                    internal_state=wf_state,
                    workflow_id=wf_id,
                    approval_id=approval_id,
                    gate=gate,
                )
            )

        if status_filter and status_filter != "all":
            return [c for c in candidates if c.status == status_filter]
        return candidates

    def start_auto(
        self,
        limit: int = 5,
        owner_user_id: str = "local-owner",
        target_date: date | None = None,
        worker_id: str | None = None,
        qc_authorization: dict[str, Any] | None = None,
        qc_max_cost_usd: float | None = None,
        research_snapshot_id: str | None = None,
    ) -> BatchStartResult:
        """Atomically claim and start up to `limit` eligible UNPROCESSED products.

        Strictly preserves Product-Intelligence published manifest priority.
        Does NOT rerank products.
        Enforces 1 <= limit <= 5 across the READY batch's production date.
        """
        if limit < 1 or limit > 5:
            raise ValueError(f"Limit must be between 1 and 5, got: {limit}")

        batch_dir = self.importer.find_latest_ready_batch(target_date)
        manifest = self.importer.load_manifest(batch_dir)
        effective_worker_id = worker_id or f"coord-{os.getpid()}"

        candidates = self.list_candidates(target_date)
        unprocessed = [c for c in candidates if c.status == "unprocessed"]
        already_started = sum(
            row["status"] == "started"
            for row in self.import_repo.get_all_for_date(manifest.production_date).values()
        )
        # Repeated scheduled runs may fill a shortfall, but never exceed the
        # daily cap. Keep Product-Intelligence manifest priority.
        selected = unprocessed[:max(0, limit - already_started)]

        selected_keys = [c.product_key for c in selected]
        return self._start_products_by_keys(
            product_keys=selected_keys,
            manifest=manifest,
            batch_dir=batch_dir,
            owner_user_id=owner_user_id,
            worker_id=effective_worker_id,
            qc_authorization=qc_authorization,
            qc_max_cost_usd=qc_max_cost_usd,
            research_snapshot_id=research_snapshot_id,
        )

    def start_selection(
        self,
        product_keys: list[str],
        owner_user_id: str = "local-owner",
        target_date: date | None = None,
        worker_id: str | None = None,
        qc_authorization: dict[str, Any] | None = None,
        qc_max_cost_usd: float | None = None,
        research_snapshot_id: str | None = None,
    ) -> BatchStartResult:
        """Start workflows for a specific set of selected product keys with write-time revalidation."""
        deduped = list(dict.fromkeys(product_keys))
        if len(deduped) > 5:
            raise ValueError(f"Cannot select more than 5 products at a time, got: {len(deduped)}")
        if not deduped:
            return BatchStartResult(started=(), skipped=())

        batch_dir = self.importer.find_latest_ready_batch(target_date)
        manifest = self.importer.load_manifest(batch_dir)
        effective_worker_id = worker_id or f"coord-{os.getpid()}"

        return self._start_products_by_keys(
            product_keys=deduped,
            manifest=manifest,
            batch_dir=batch_dir,
            owner_user_id=owner_user_id,
            worker_id=effective_worker_id,
            qc_authorization=qc_authorization,
            qc_max_cost_usd=qc_max_cost_usd,
            research_snapshot_id=research_snapshot_id,
        )

    def _start_products_by_keys(
        self,
        product_keys: list[str],
        manifest: Any,
        batch_dir: Path,
        owner_user_id: str,
        worker_id: str,
        qc_authorization: dict[str, Any] | None = None,
        qc_max_cost_usd: float | None = None,
        research_snapshot_id: str | None = None,
    ) -> BatchStartResult:
        prod_by_key = {p.product_key: p for p in manifest.products}
        prod_by_canon = {p.canonical_product_key: p for p in manifest.products}
        started: list[StartedProduct] = []
        skipped: list[SkippedProduct] = []

        for key_req in product_keys:
            product = prod_by_key.get(key_req) or prod_by_canon.get(key_req)
            if product is None:
                skipped.append(SkippedProduct(product_key=key_req, reason="NOT_FOUND_IN_MANIFEST"))
                continue

            pkey = product.product_key

            is_valid, reason, valid_imgs = self.importer.validate_admission(product, batch_dir)
            if not is_valid:
                skipped.append(SkippedProduct(product_key=pkey, reason=f"INVALID_ADMISSION: {reason}"))
                continue

            # Atomic claim under immediate transaction
            claim = self.import_repo.claim_product(
                canonical_product_key=product.canonical_product_key,
                source_date=manifest.production_date,
                source_batch_id=manifest.batch_id,
                source_product_id=product.source_product_id,
                source_path=str(batch_dir / "manifest.json"),
                worker_id=worker_id,
            )

            if claim.status != "claimed":
                if claim.status == "already_started":
                    reason = "ALREADY_STARTED"
                elif claim.status == "already_claimed":
                    reason = "ALREADY_CLAIMED"
                else:
                    reason = f"CLAIM_ERROR: {claim.error or claim.status}"
                skipped.append(SkippedProduct(
                    product_key=pkey,
                    reason=reason,
                    workflow_id=claim.workflow_id,
                    error=claim.error,
                ))
                continue

            workflow_id = claim.workflow_id
            exact_identity = f"{product.brand} {product.model}".strip()
            keywords = list(dict.fromkeys([exact_identity, str(product.name), *(product.keywords or [])]))
            source_context = {
                "source": "hermes_product_video_exchange",
                "source_date": manifest.production_date,
                "source_batch_id": manifest.batch_id,
                "source_file": str(batch_dir / "manifest.json"),
                "source_product_id": product.source_product_id,
                "canonical_product_key": product.canonical_product_key,
                "product_key": pkey,
                "brand": product.brand,
                "model": product.model,
                "variant": product.variant,
                "hot_reason": product.hot_reason,
                "key_features": product.key_features,
                "images": valid_imgs,
            }

            try:
                start_product_video_workflow(
                    workflow_repository=self.workflow_repo,
                    workflow_id=workflow_id,
                    product_name=str(product.name),
                    keywords=keywords,
                    pdp_url=product.source_url,
                    owner_user_id=owner_user_id,
                    idempotency_key=f"exchange-import:{pkey}",
                    project_id=f"proj-{workflow_id}",
                    source_context=source_context,
                    qc_authorization=qc_authorization,
                    qc_max_cost_usd=qc_max_cost_usd,
                    research_snapshot_id=research_snapshot_id,
                )
                self.import_repo.mark_started(pkey)
                started.append(StartedProduct(
                    product_key=pkey,
                    canonical_product_key=product.canonical_product_key,
                    workflow_id=workflow_id,
                    name=product.name,
                ))
            except Exception as exc:  # noqa: BLE001
                if self.workflow_repo.get_workflow(workflow_id) is not None:
                    # Recovery: Workflow was created before worker crashed; mark started safely
                    self.import_repo.mark_started(pkey)
                    started.append(StartedProduct(
                        product_key=pkey,
                        canonical_product_key=product.canonical_product_key,
                        workflow_id=workflow_id,
                        name=product.name,
                    ))
                else:
                    self.import_repo.mark_error(pkey, str(exc))
                    skipped.append(SkippedProduct(
                        product_key=pkey,
                        reason=f"START_FAILED: {exc}",
                        workflow_id=workflow_id,
                        error=str(exc),
                    ))

        return BatchStartResult(started=tuple(started), skipped=tuple(skipped))

    def advance_to_product_lock(
        self,
        workflow_ids: list[str],
        provider_mode: str = "configured",
        max_cycles: int = 10,
    ) -> dict[str, Any]:
        """Drive newly started workflows to AwaitingProductLock via durable outbox.

        Only targets the specified workflow_ids.
        Returns a structured report.
        """
        if not workflow_ids:
            return {"succeeded": True, "workflows": {}}

        from hermes_personal.application.operator_handler import ApprovalService

        effective_db_path = self.db_path
        if effective_db_path is None:
            rows = self.connection.execute("PRAGMA database_list").fetchall()
            for r in rows:
                if (r["name"] if hasattr(r, "keys") else r[1]) == "main":
                    file_path = r["file"] if hasattr(r, "keys") else r[2]
                    if file_path:
                        effective_db_path = Path(file_path)
                    break

        if effective_db_path is None:
            raise ValueError("db_path required for advance_to_product_lock")

        wf_states: dict[str, Any] = {}
        approval_svc = ApprovalService(self.connection)

        for cycle in range(max_cycles):
            report = run_worker(
                db_path=effective_db_path,
                provider_mode=provider_mode,
                once=True,
                batch_size=len(workflow_ids) * 2,
                workflow_ids=workflow_ids,
            )

            all_at_lock = True
            has_failure = False

            for wf_id in workflow_ids:
                wf_data = self.workflow_repo.get_workflow(wf_id)
                if not wf_data:
                    all_at_lock = False
                    wf_states[wf_id] = {"state": "missing", "error": "Workflow aggregate not found"}
                    has_failure = True
                    continue

                agg, ver = wf_data
                state = agg.get("state")
                approval_id = agg.get("pending_approval_id")
                gate = agg.get("pending_approval_gate")

                if state == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value or state == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK:
                    if not approval_id:
                        all_at_lock = False
                        wf_states[wf_id] = {"state": state, "error": "Missing pending_approval_id"}
                        has_failure = True
                    else:
                        req = approval_svc.get_request(approval_id)
                        if not req or req.status.value != "pending":
                            all_at_lock = False
                            wf_states[wf_id] = {"state": state, "error": f"Approval request not pending: {req.status if req else None}"}
                            has_failure = True
                        else:
                            wf_states[wf_id] = {"state": state, "approval_id": approval_id, "gate": gate}
                else:
                    all_at_lock = False
                    wf_states[wf_id] = {"state": state}

            if has_failure:
                return {
                    "succeeded": False,
                    "error": "One or more workflows encountered an error or invalid state",
                    "workflows": wf_states,
                }

            if all_at_lock:
                return {
                    "succeeded": True,
                    "cycles": cycle + 1,
                    "workflows": wf_states,
                }

            if report and report.succeeded == 0 and report.failed == 0 and report.claimed == 0:
                return {
                    "succeeded": False,
                    "error": "No further outbox messages eligible, but workflows have not reached AwaitingProductLock",
                    "workflows": wf_states,
                }

        return {
            "succeeded": False,
            "error": f"Exceeded maximum cycles ({max_cycles}) advancing to Product Lock",
            "workflows": wf_states,
        }


    def approve_product_lock(
        self,
        target_id: str,
        owner_user_id: str = "local-owner",
    ) -> dict[str, Any]:
        """Approve Product Lock gate and resume the existing state machine.

        Guarantees that approval only advances the workflow state to BUILDING_RESOURCE_PACK
        and enqueues the next outbox job, with NO alternate fast-path bypassing the worker.
        """
        return approve_and_advance_workflow(
            connection=self.connection,
            target_id=target_id,
            owner_user_id=owner_user_id,
        )

    def get_workflow_status(self, workflow_id: str) -> dict[str, Any] | None:
        """Inspect workflow aggregate status, approval details, and research snapshot."""
        wf_data = self.workflow_repo.get_workflow(workflow_id)
        if wf_data is None:
            return None
        agg, version = wf_data

        pending_app_id = agg.get("pending_approval_id")
        approval_dict = None
        if pending_app_id:
            try:
                from hermes_personal.workflows.approvals import ApprovalService

                app_svc = ApprovalService(self.connection)
                req = app_svc.get_request(pending_app_id)
                approval_dict = {
                    "request_id": req.request_id,
                    "status": req.status.value,
                    "gate": req.payload.get("gate", agg.get("pending_approval_gate")),
                    "created_at": req.created_at,
                    "updated_at": req.updated_at,
                    "payload": req.payload,
                }
            except Exception:
                pass

        events = []
        try:
            cur = self.connection.execute(
                "SELECT event_id, event_type, timestamp, payload_json FROM workflow_event WHERE workflow_id = ? ORDER BY timestamp DESC LIMIT 10",
                (workflow_id,),
            )
            for r in cur.fetchall():
                events.append({
                    "event_id": r[0],
                    "event_type": r[1],
                    "timestamp": r[2],
                    "payload": json.loads(r[3]) if r[3] else {},
                })
        except Exception:
            pass

        latest_art = agg.get("latest_artifact")
        research_snapshot = None
        if latest_art and isinstance(latest_art, dict):
            rep = latest_art.get("report")
            rep_data = json.loads(rep) if isinstance(rep, str) else (rep or {})
            research_snapshot = {
                "snapshot_id": latest_art.get("snapshot_id") or rep_data.get("snapshot_id"),
                "status": rep_data.get("status"),
                "summary": rep_data.get("summary") or latest_art.get("summary"),
                "source_summary": rep_data.get("source_summary"),
                "discovered_sources": rep_data.get("discovered_sources", []),
                "canonical_products": rep_data.get("canonical_products", []),
                "media_assets": rep_data.get("media_assets", []),
                "warnings": rep_data.get("warnings", []),
                "conflicts": rep_data.get("conflicts", []),
                "facts": rep_data.get("key_facts") or rep_data.get("facts", []),
                "selling_points": rep_data.get("selling_points") or rep_data.get("selling_angles", []),
                "competitors": rep_data.get("competitors", []),
                "risks": rep_data.get("risks") or rep_data.get("concerns", []),
            }

        return {
            "workflow_id": workflow_id,
            "version": version,
            "state": agg.get("state"),
            "pending_approval_gate": agg.get("pending_approval_gate"),
            "pending_approval_id": pending_app_id,
            "product_key": agg.get("product_key"),
            "source_context": agg.get("source_context"),
            "latest_artifact": latest_art,
            "approval": approval_dict,
            "events": events,
            "research_snapshot": research_snapshot,
        }

    def run_research_worker(
        self,
        provider_mode: str = "configured",
        batch_size: int = 5,
        once: bool = True,
    ) -> Any:
        """Run durable worker one-shot to advance research jobs up to AwaitingProductLock."""
        if not self.db_path:
            raise ValueError("db_path required to launch durable worker")
        return run_worker(
            db_path=self.db_path,
            provider_mode=provider_mode,
            once=once,
            batch_size=batch_size,
            workflow_id_prefix="pv-daily-",
        )
