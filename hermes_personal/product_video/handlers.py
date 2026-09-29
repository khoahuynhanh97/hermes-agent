from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from hermes_personal.integrations.product_intelligence.client import ProductIntelligenceClient
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.capabilities.snapshots import CatalogSnapshot
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.workflows.approvals import ApprovalService
from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget, get_reservation
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.envelope import (
    MalformedEnvelopeError,
    OutboxEnvelope,
    build_envelope,
)
from hermes_personal.product_video.qc.models import QCReport, QCStage, QCVerdict
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.job_contracts import (
    ExecutionBindingPreflight,
    ExecutionBindingPreflightError,
    JobContext,
    JobDispatchError,
    JobFailed,
    JobSucceeded,
    LeaseLostError,
    TerminalJobError,
)
from hermes_personal.product_video.workflow_state import (
    HITL_WAITING_STATES,
    ProductVideoWorkflowState,
)
from hermes_personal.product_video.provider_runtime import (
    resolve_polling_setting,
    resolve_provider_mode,
    validate_polling_setting,
    validate_provider_mode,
)
from hermes_personal.product_video.mcp_adapters import (
    MCPProductIntelligenceAdapter,
    MCPVideoFactoryAdapter,
    _check_for_errors,
    _decode_mcp_output,
    _dispatch_tool,
    _get_global_tool_registry,
    _get_tool_names_from_registry,
    _require_snapshot_wire,
    _resolve_snapshot_execution_wire,
)

from hermes_personal.workflows.jobs import JobDispatcher, JobResult, JobSpec, JobStatus
from hermes_personal.workflows.repository import WorkflowRepository


def _qc_context(data: dict[str, Any], workflow_id: str | None = None) -> dict[str, Any]:
    res: dict[str, Any] = {}
    auth = data.get("qc_authorization")
    if isinstance(auth, dict):
        auth_dict = dict(auth)
        if workflow_id and "workflow_id" not in auth_dict:
            auth_dict["workflow_id"] = workflow_id
        res["qc_authorization"] = auth_dict
    max_cost = data.get("qc_max_cost_usd")
    if max_cost is not None:
        try:
            res["qc_max_cost_usd"] = float(max_cost)
        except (ValueError, TypeError):
            pass
    return res


def _paid_budget_kwargs(
    ctx: "JobContext",
    capability_id: str,
    kwargs: dict[str, Any],
    operation_input_digest: str | None = None,
) -> dict[str, Any]:
    """Bind every paid reservation to its workflow and optional operator grant."""
    result: dict[str, Any] = {
        "owner_user_id": ctx.owner_user_id,
        "scope_id": ctx.workflow_id,
        "capability_id": capability_id,
        "operation_input_digest": operation_input_digest or ctx.idempotency_key or ctx.job_id,
        "attempt_id": f"{ctx.workflow_id}:{capability_id.rsplit('.', 1)[-1]}:{ctx.job_id}",
    }
    authorization = kwargs.get("qc_authorization")
    if not isinstance(authorization, dict):
        return result

    authorization_id = str(
        authorization.get("authorization_id") or authorization.get("run_id") or ""
    ).strip()
    if authorization_id:
        result["authorization_id"] = authorization_id
        result["external_reference"] = authorization_id

    campaign_id = str(authorization.get("campaign_id") or "product-video-default").strip()
    if campaign_id:
        result["campaign_id"] = campaign_id

    def _usd_to_cents(value: Any) -> int | None:
        try:
            cents = int(round(float(value) * 100))
        except (TypeError, ValueError):
            return None
        return cents if cents > 0 else None

    campaign_max = _usd_to_cents(authorization.get("campaign_max_cost_usd"))
    if campaign_max is not None:
        result["campaign_max"] = campaign_max
    scope_max = _usd_to_cents(
        authorization.get("workflow_max_cost_usd", authorization.get("max_cost_usd"))
    )
    if scope_max is not None:
        result["scope_max"] = scope_max
    return result


def _is_qc_pass(qc_res: Any) -> bool:
    if not isinstance(qc_res, dict):
        return False
    if qc_res.get("status") != "completed":
        return False
    rep = qc_res.get("report")
    verdict = None
    if rep is not None:
        if isinstance(rep, dict):
            verdict = rep.get("verdict")
        elif hasattr(rep, "verdict"):
            verdict = getattr(rep, "verdict")
    if verdict is None:
        verdict = qc_res.get("verdict")
    if hasattr(verdict, "value"):
        verdict = verdict.value
    return str(verdict).lower() == "pass"


def _qc_report_payload(qc_res: Any) -> dict[str, Any]:
    if not isinstance(qc_res, dict):
        return {}
    rep = qc_res.get("report")
    if isinstance(rep, dict):
        return rep
    if hasattr(rep, "verdict"):
        v = rep.verdict
        if hasattr(v, "value"):
            v = v.value
        stage = getattr(rep, "stage", None)
        if hasattr(stage, "value"):
            stage = stage.value
        return {
            "report_id": getattr(rep, "report_id", qc_res.get("report_id")),
            "workflow_id": getattr(rep, "workflow_id", None),
            "stage": stage,
            "verdict": v,
            "score": getattr(rep, "score", 0),
            "artifact_id": getattr(rep, "artifact_id", None),
            "artifact_version": getattr(rep, "artifact_version", None),
            "artifact_digest": getattr(rep, "artifact_digest", None),
            "findings": getattr(rep, "findings", {}),
            "hard_failure": getattr(rep, "hard_failure", False),
        }
    return qc_res


def _video_factory_brief_config(
    base_config: dict[str, Any],
    brief: Any,
) -> dict[str, Any]:
    """Project a grounded V2 brief onto Video Factory's persisted brief contract."""
    audience = getattr(brief, "audience")
    reasons = getattr(brief, "reason_to_believe")
    return {
        **base_config,
        "objective": brief.creative_angle,
        "target_audience": f"{audience.segment} — {audience.situation}",
        "core_message": brief.promise,
        "tone": brief.tone,
        "pace": "Nhanh gọn, đời thường",
        "cta": brief.cta,
        "content_blocks": [brief.hook, brief.problem, brief.promise],
        "verified_selling_points": [
            {
                "claim": reason.text,
                "status": "verified",
                "evidence_refs": list(reason.evidence_refs),
            }
            for reason in reasons
        ],
        "restrictions": list(brief.restrictions),
        "target_duration_seconds": brief.target_duration_seconds,
    }


def create_configured_creative_generator() -> Any:
    """Build the single-model grounded creative boundary from user configuration.

    Defaults select the already-supported Vertex route for the personal MVP;
    provider and model remain overridable in ``config.yaml`` at
    ``product_video.creative``. Credentials are deliberately left to Hermes'
    provider resolver rather than duplicated in this workflow package.
    """
    from hermes_cli.config import load_config_readonly
    from hermes_personal.product_video.creative.generator import SingleModelCreativeGenerator
    from hermes_personal.product_video.creative.model_adapter import HermesStructuredCreativeModel

    config = load_config_readonly()
    product_video = config.get("product_video") if isinstance(config, dict) else None
    creative = product_video.get("creative") if isinstance(product_video, dict) else None
    provider = str(creative.get("provider") or "vertex") if isinstance(creative, dict) else "vertex"
    model = str(creative.get("model") or "google/gemini-2.5-flash") if isinstance(creative, dict) else "google/gemini-2.5-flash"
    timeout = 120.0
    if isinstance(creative, dict) and creative.get("timeout_seconds") is not None:
        timeout = validate_polling_setting("creative.timeout_seconds", creative["timeout_seconds"], timeout)
    return SingleModelCreativeGenerator(
        HermesStructuredCreativeModel(
            provider=provider,
            model=model,
            timeout=timeout,
        )
    )


def _brand_owned_product_url(brand: str, url: str) -> bool:
    """Recognize an HTTPS brand.com source when PI left its class unknown."""
    brand_domain = "".join(char for char in brand.casefold() if char.isascii() and char.isalnum())
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    return bool(brand_domain) and parsed.scheme == "https" and host == f"{brand_domain}.com"


def _locked_research_dossier(
    *,
    workflow_id: str,
    aggregate: dict[str, Any],
    locked_pack: dict[str, Any],
    connection: Any,
) -> dict[str, Any]:
    """Build the immutable creative input from locked PI data and Image QC."""
    from hermes_personal.product_video.creative.dossier import build_research_dossier

    resource_pack = dict(aggregate.get("resource_pack") or {})
    pack_raw = resource_pack.get("raw_result")
    if isinstance(pack_raw, dict):
        resource_pack = {**resource_pack, **pack_raw}
    locked_raw = locked_pack.get("raw_result")
    if isinstance(locked_raw, dict):
        resource_pack = {**resource_pack, **locked_raw}
    source_context = aggregate.get("source_context")
    if not isinstance(source_context, dict):
        source_context = {}
    identity = resource_pack.get("product_identity")
    if not isinstance(identity, dict):
        identity = {}
    locked_identity = resource_pack.get("locked_product_identity")
    if not isinstance(locked_identity, dict):
        locked_identity = {}
    resolved = resource_pack.get("resolved_values")
    if not isinstance(resolved, dict):
        resolved = {}
    brand = str(identity.get("brand") or resolved.get("brand") or source_context.get("brand") or "").strip()
    model = str(identity.get("model") or resolved.get("model") or source_context.get("model") or "").strip()
    display_name = str(identity.get("name") or identity.get("display_name") or resolved.get("name") or f"{brand} {model}".strip()).strip()
    resource_pack["product_identity"] = {
        "brand": brand,
        "model": model,
        "display_name": display_name,
        "variant": str(
            identity.get("variant")
            or resolved.get("variant")
            or source_context.get("variant")
            or ""
        ),
        "distinctive_features": list(
            identity.get("distinctive_features")
            or locked_identity.get("distinctive_features")
            or []
        ),
        "shape": str(identity.get("shape") or locked_identity.get("shape") or ""),
        "color": str(identity.get("color") or locked_identity.get("color") or ""),
        "materials": str(
            identity.get("materials")
            or identity.get("material")
            or locked_identity.get("materials")
            or locked_identity.get("material")
            or ""
        ),
        "logo_placement": str(
            identity.get("logo_placement") or locked_identity.get("logo_placement") or ""
        ),
        "silhouette": str(
            identity.get("silhouette") or locked_identity.get("silhouette") or ""
        ),
        "main_proportions": str(
            identity.get("main_proportions")
            or locked_identity.get("main_proportions")
            or ""
        ),
        "product_count": str(
            identity.get("product_count") or locked_identity.get("product_count") or ""
        ),
        "control_placement": str(
            identity.get("control_placement")
            or locked_identity.get("control_placement")
            or ""
        ),
        "port_count": str(
            identity.get("port_count") or locked_identity.get("port_count") or ""
        ),
        "port_placement": str(
            identity.get("port_placement") or locked_identity.get("port_placement") or ""
        ),
        "display_shape": str(
            identity.get("display_shape") or locked_identity.get("display_shape") or ""
        ),
    }

    research_result = aggregate.get("research_result")
    research_report: dict[str, Any] = {}
    if isinstance(research_result, dict):
        raw_report = research_result.get("report")
        if isinstance(raw_report, str):
            try:
                parsed = json.loads(raw_report)
                if isinstance(parsed, dict):
                    research_report = parsed
            except json.JSONDecodeError:
                pass
    research_raw = research_result.get("raw_result") if isinstance(research_result, dict) else None
    if not isinstance(research_raw, dict):
        research_raw = research_report
    source_results = resource_pack.get("source_results") or research_raw.get("source_results") or research_report.get("source_results") or []
    discovered = resource_pack.get("discovered_sources") or research_raw.get("discovered_sources") or research_report.get("discovered_sources") or []
    usable_urls = {
        str(url)
        for item in source_results
        if isinstance(item, dict)
        and (item.get("usable") is True or item.get("acquisition_status") == "usable")
        for url in (item.get("requested_url"), item.get("final_url"), item.get("canonical_url"), item.get("url"))
        if url
    }
    official_sources = sorted({
        str(item.get("url"))
        for item in discovered
        if isinstance(item, dict)
        and str(item.get("source_class") or "").lower() in {"official", "manufacturer", "brand_official"}
        and item.get("url")
        and str(item["url"]) in usable_urls
    } | {
        str(item.get("url"))
        for item in source_results
        if isinstance(item, dict)
        and str(item.get("source_class") or "").lower() in {"official", "manufacturer", "brand_official"}
        and item.get("url")
        and str(item["url"]) in usable_urls
    } | {
        str(item.get("url"))
        for item in source_results
        if isinstance(item, dict)
        and str(item.get("source_class") or "").lower() == "unknown"
        and item.get("url")
        and str(item["url"]) in usable_urls
        and _brand_owned_product_url(brand, str(item["url"]))
    })
    evidence_items = resource_pack.get("evidence") or research_raw.get("evidence") or research_raw.get("product_evidence") or []
    evidence_by_id = {
        str(item.get("evidence_id") or item.get("id")): item
        for item in evidence_items
        if isinstance(item, dict) and (item.get("evidence_id") or item.get("id"))
    }
    snapshot_id = str(resource_pack.get("snapshot_id") or "")
    product_id = str(resource_pack.get("canonical_product_id") or "")
    variant_id = str(resource_pack.get("variant_id") or "")
    claims = []
    seen_claims: set[tuple[str, tuple[str, ...]]] = set()
    for item in resource_pack.get("claims") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("claim") or "").strip()
        claim_id = str(item.get("claim_id") or item.get("id") or "").strip()
        status = str(item.get("support_status") or item.get("status") or "").lower()
        refs = item.get("evidence_refs") or item.get("source_evidence_ids") or []
        if not (text and claim_id and status in {"supported", "verified", "confirmed", "verified_spec", "source_claim"}):
            continue
        if not isinstance(refs, (list, tuple)) or not refs:
            continue
        normalized_refs = tuple(str(ref).strip() for ref in refs if str(ref).strip())
        if not normalized_refs or len(normalized_refs) != len(refs):
            continue
        if any(
            ref not in evidence_by_id
            or not snapshot_id
            or not product_id
            or str(evidence_by_id[ref].get("snapshot_id") or "") != snapshot_id
            or str(evidence_by_id[ref].get("canonical_product_id") or "") != product_id
            or (variant_id and str(evidence_by_id[ref].get("variant_id") or "") not in {"", variant_id})
            for ref in normalized_refs
        ):
            continue
        if status == "source_claim" and any(
            not {
                str((evidence_by_id[ref].get("source") or {}).get(field) or "")
                for field in ("canonical_url", "final_url", "requested_url")
            }.intersection(official_sources)
            for ref in normalized_refs
        ):
            continue
        if any(
            str(item.get(field) or "") not in {"", expected}
            for field, expected in (
                ("snapshot_id", snapshot_id),
                ("canonical_product_id", product_id),
                ("variant_id", variant_id),
            )
        ):
            continue
        claim_key = (" ".join(text.casefold().split()), normalized_refs)
        if claim_key in seen_claims:
            continue
        seen_claims.add(claim_key)
        claims.append({
            "claim_id": claim_id,
            "text": text,
            "status": "supported",
            "evidence_refs": list(normalized_refs),
        })
    report = QCReportRepository(connection).get_latest_report(workflow_id, QCStage.IMAGE)
    if report is None or report.verdict != QCVerdict.PASS:
        raise ValueError("a passing persisted Image QC report is required before creative generation")
    return build_research_dossier(
        workflow_id=workflow_id,
        resource_pack=resource_pack,
        qc_report=report,
        research_snapshot={
            "claims": claims,
            "source_refs": official_sources,
            # Candidate hot_reason is scouting copy, not claim-level PI evidence.
            # Passing it as a use case lets creative generation promote unverified
            # health or performance promises into the approved dossier.
            "use_cases": [],
        },
    ).to_dict()


def _confirm_vf_storyboard_write(
    result: Any,
    *,
    owner_user_id: str,
    project_id: str,
    scene_ids: tuple[str, ...],
) -> None:
    """Require the VF response to describe the matching canonical write."""
    if not isinstance(result, dict):
        raise ValueError("VF storyboard write returned no canonical result")
    raw = result
    if isinstance(result.get("payload"), str):
        try:
            raw = json.loads(result["payload"])
        except json.JSONDecodeError as exc:
            raise ValueError("VF storyboard write returned an invalid payload") from exc
    if not isinstance(raw, dict) or raw.get("ok") is not True:
        reason = raw.get("error") if isinstance(raw, dict) else None
        raise ValueError(f"VF storyboard write failed for {project_id}: {reason or 'unconfirmed result'}")
    project = raw.get("project")
    if (
        raw.get("project_id") != project_id
        or not isinstance(project, dict)
        or project.get("id") != project_id
        or project.get("owner_user_id") != owner_user_id
        or project.get("scene_plan_approval") != "approved"
    ):
        raise ValueError(f"VF storyboard write identity mismatch for {project_id}")
    storyboard = project.get("storyboard")
    if (
        not isinstance(storyboard, dict)
        or not storyboard.get("storyboard_id")
        or storyboard.get("storyboard_id") != raw.get("storyboard_id")
    ):
        raise ValueError(f"VF storyboard write was not persisted for {project_id}")
    scene_plan = project.get("scene_plan")
    if not isinstance(scene_plan, dict):
        raise ValueError(f"VF approved scene plan is missing for {project_id}")
    for label, frames in (
        ("scene plan", scene_plan.get("scenes")),
        ("storyboard", storyboard.get("frames")),
        ("response", raw.get("frames")),
    ):
        if (
            not isinstance(frames, list)
            or tuple(item.get("scene_id") for item in frames if isinstance(item, dict))
            != scene_ids
        ):
            raise ValueError(f"VF {label} scenes do not match approved plan for {project_id}")


def _recover_creative_brief(
    persisted: dict[str, Any],
    dossier: Any,
) -> Any | None:
    """Rebuild a V2 artifact after a crash following an already persisted brief.

    The recovery provenance makes clear that the original raw model response
    was not durably captured before the process failed; it must never be
    presented as a fresh model invocation.
    """
    from hermes_personal.product_video.creative.contracts import (
        AudienceSpec,
        CreativeBriefV2,
        GenerationProvenance,
        ReasonToBelieve,
    )

    target = str(persisted.get("target_audience") or "").strip()
    segment, separator, situation = target.partition("—")
    reasons = []
    for item in persisted.get("verified_selling_points") or []:
        if not isinstance(item, dict):
            continue
        refs = tuple(str(ref) for ref in item.get("evidence_refs") or [] if str(ref).strip())
        claim = str(item.get("claim") or "").strip()
        if claim and refs:
            reasons.append(ReasonToBelieve(text=claim, evidence_refs=refs))
    blocks = [str(item).strip() for item in persisted.get("content_blocks") or [] if str(item).strip()]
    if not (target and reasons and blocks):
        return None
    try:
        return CreativeBriefV2.create(
            audience=AudienceSpec(
                segment=segment.strip(),
                situation=(situation if separator else "Product use").strip(),
                desired_outcome=str(persisted.get("core_message") or "").strip(),
            ),
            consumer_insight=blocks[1] if len(blocks) > 1 else blocks[0],
            problem=blocks[1] if len(blocks) > 1 else blocks[0],
            creative_angle=str(persisted.get("objective") or "").strip(),
            hook=blocks[0],
            promise=str(persisted.get("core_message") or "").strip(),
            reason_to_believe=tuple(reasons),
            tone=str(persisted.get("tone") or "").strip(),
            story_archetype="problem_solution_demo",
            cta=str(persisted.get("cta") or "").strip(),
            restrictions=tuple(str(item) for item in persisted.get("restrictions") or []),
            target_duration_seconds=int(persisted.get("target_duration_seconds") or 20),
            dossier_digest=dossier.digest(),
            provenance=GenerationProvenance(
                prompt_version="creative-direction-v2",
                provider="recovered_video_factory",
                model="",
                input_digests=(dossier.digest(),),
                parse_error="Recovered after Video Factory persisted the brief before the budget commit completed.",
            ),
        )
    except (TypeError, ValueError):
        return None


def _require_configured_execution_binding(
    client: Any,
    stage_key: str,
    capability_id: str,
) -> str:
    """Fail closed when a configured client cannot prove its execution binding.

    This is deliberately a structural capability check rather than a concrete
    adapter check: every configured client that can submit paid work must make
    the same immutable-binding guarantee.
    """
    try:
        preflight = getattr(client, "require_execution_binding", None)
    except Exception as exc:
        raise ExecutionBindingPreflightError(capability_id, exc) from exc
    if not callable(preflight):
        raise TerminalJobError(
            f"BINDING_UNAVAILABLE: Configured video client is missing execution binding "
            f"preflight for capability '{capability_id}' (missing_preflight_contract)",
            code="BINDING_UNAVAILABLE",
        )
    try:
        wire = preflight(stage_key, capability_id)
    except TerminalJobError:
        raise
    except Exception as exc:
        raise ExecutionBindingPreflightError(capability_id, exc) from exc
    if not isinstance(wire, str) or not wire.strip():
        raise TerminalJobError(
            f"BINDING_UNAVAILABLE: Configured video client returned no execution wire "
            f"for capability '{capability_id}' (invalid_preflight_result)",
            code="BINDING_UNAVAILABLE",
        )
    if capability_id == "video.render" and wire != "mcp__video_factory__render":
        raise TerminalJobError(
            f"BINDING_UNAVAILABLE: Configured video client returned a noncanonical "
            f"execution wire for capability '{capability_id}' (noncanonical_wire)",
            code="BINDING_UNAVAILABLE",
        )
    return wire


def _resolve_durable_resume_job_id(
    params: dict[str, Any],
    aggregate: dict[str, Any],
    durable_job_key: str,
    forbidden_aliases: tuple[str, ...] = (),
) -> str:
    """Return the only identity eligible for a no-resubmit resume.

    An externally supplied job ID is never authoritative: it must match the
    durable checkpoint exactly after normalization. A missing requested ID
    resumes the durable identity when one exists.
    """
    noncanonical_aliases = [
        alias
        for alias in forbidden_aliases
        if str(params.pop(alias, "") or "").strip()
    ]
    if noncanonical_aliases:
        raise TerminalJobError(
            f"Noncanonical resume identity field(s) {', '.join(noncanonical_aliases)} "
            "are not supported at the workflow boundary "
            "(noncanonical_resume_identity)",
            code="JOB_BINDING_MISMATCH",
        )

    requested_job_id = str(params.get("active_job_id") or "").strip()
    durable_job_id = str(aggregate.get(durable_job_key) or "").strip()
    if requested_job_id and requested_job_id != durable_job_id:
        reason = "unbound_durable_identity" if not durable_job_id else "durable_identity_mismatch"
        raise TerminalJobError(
            f"Requested active_job_id '{requested_job_id}' does not match durable "
            f"job identity '{durable_job_id}' ({reason})",
            code="JOB_BINDING_MISMATCH",
        )
    if durable_job_id:
        params["active_job_id"] = durable_job_id
    else:
        params.pop("active_job_id", None)
    return durable_job_id


def _compute_digest(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def verify_job_digests(job_name: str, inputs: dict[str, Any], expected_digests: dict[str, str]) -> bool:
    for key, expected in expected_digests.items():
        if key not in inputs:
            return False
        if _compute_digest(inputs[key]) != expected:
            return False
    return True





class ProductVideoJobHandlers:
    """Deterministic product-to-video job handlers with injected dependencies and workflow state loading."""

    def __init__(
        self,
        pi_client: ProductIntelligenceClient | None = None,
        video_client: VideoFactoryClient | None = None,
        workflow_engine: WorkflowEngine | None = None,
        workflow_repository: WorkflowRepository | None = None,
        dispatcher: JobDispatcher | None = None,
        tool_registry: Any | None = None,
        provider_mode: str = "fake",
        poll_timeout: float = 60.0,
        poll_interval: float = 0.5,
        creative_generator: Any | None = None,
        keyframe_runtime_factory: Callable[[], Any] | None = None,
        capability_snapshot: CatalogSnapshot | None = None,
    ) -> None:
        self.provider_mode = validate_provider_mode(provider_mode)
        self.tool_registry = tool_registry
        self.poll_timeout = validate_polling_setting("poll_timeout", poll_timeout, 60.0)
        self.poll_interval = validate_polling_setting("poll_interval", poll_interval, 0.5)
        self.creative_generator = creative_generator
        self.keyframe_runtime_factory = keyframe_runtime_factory
        self.capability_snapshot = capability_snapshot

        if self.provider_mode == "configured":
            if pi_client is None:
                pi_client = self._resolve_pi_adapter(tool_registry)
            if video_client is None:
                video_client = self._resolve_video_adapter(tool_registry)

            self._missing_pi_provider = pi_client is None
            self._missing_video_provider = video_client is None
            self._missing_live_provider = (
                self._missing_pi_provider or self._missing_video_provider
            )
            if self._missing_live_provider:
                missing = []
                if pi_client is None:
                    missing.append("ProductIntelligence active capability binding")
                if video_client is None:
                    missing.append("VideoFactory active capability binding (canonical mcp__video_factory__render required)")
                self._missing_provider_details = ", ".join(missing)
            else:
                self._missing_provider_details = None
        else:
            self._missing_pi_provider = False
            self._missing_video_provider = False
            self._missing_live_provider = False
            self._missing_provider_details = None

        self.pi_client = pi_client or ProductIntelligenceClient()
        self.video_client = video_client or VideoFactoryClient()
        self.workflow_engine = workflow_engine
        self.workflow_repository = workflow_repository or (workflow_engine.repo if workflow_engine else None)
        self.dispatcher = dispatcher
        self._idempotency_cache: dict[str, JobSucceeded] = {}

    def _resolve_pi_adapter(self, registry: Any | None) -> Any | None:
        effective_registry = registry or _get_global_tool_registry()
        if effective_registry is None or self.capability_snapshot is None:
            return None
        capability_keys = {
            "research": "product.research",
            "build_resource_pack": "product.resource_pack.build",
            "lock_resource_pack": "product.resource_pack.lock",
        }
        resolved = {
            key: _resolve_snapshot_execution_wire(self.capability_snapshot, capability_id)
            for key, capability_id in capability_keys.items()
        }
        return MCPProductIntelligenceAdapter(
            effective_registry,
            {
                key: wire for key, (wire, _reason) in resolved.items() if wire
            } | {"get_research": "mcp__product_intelligence__get_product_research"},
            {key: reason for key, (_wire, reason) in resolved.items() if reason},
        )

    def _resolve_video_adapter(self, registry: Any | None) -> Any | None:
        effective_registry = registry or _get_global_tool_registry()
        if effective_registry is None or self.capability_snapshot is None:
            return None
        capability_keys = {
            "brief": "video.brief.create",
            "scene_plan": "video.scene_plan.create",
            "storyboard": "video.storyboard.create",
            "render": "video.render",
            "export": "video.export",
        }
        resolved = {
            key: _resolve_snapshot_execution_wire(self.capability_snapshot, capability_id)
            for key, capability_id in capability_keys.items()
        }
        # Execution-stage wires come only from the active snapshot. The
        # remaining static names are non-capability factory maintenance/status
        # calls and are never selected by alias preference.
        wire_map = {
            key: wire for key, (wire, _reason) in resolved.items() if wire
        }
        render_wire = wire_map.get("render")
        if render_wire is not None and render_wire != "mcp__video_factory__render":
            wire_map.pop("render")
        wire_map.update(
            {
                "project_create": "mcp__video_factory__video_project_create",
                "resource_pack_save": "mcp__video_factory__resource_pack_save",
                "resource_pack_lock": "mcp__video_factory__resource_pack_lock",
                "creative_brief_get": "mcp__video_factory__creative_brief_get",
                "brief_approve": "mcp__video_factory__creative_brief_approve",
                "scene_plan_approve": "mcp__video_factory__scene_plan_approve",
                "storyboard_approve": "mcp__video_factory__storyboard_approve",
                "final_video_approve": "mcp__video_factory__final_video_approve",
                "get_job_status": "mcp__video_factory__get_job_status",
            }
        )
        return MCPVideoFactoryAdapter(
            effective_registry,
            wire_map,
            poll_timeout=self.poll_timeout,
            poll_interval=self.poll_interval,
            binding_reasons={key: reason for key, (_wire, reason) in resolved.items() if reason},
        )


    def _get_workflow_state_and_version(self, ctx: JobContext) -> tuple[str, int] | None:
        """Load state and version through public WorkflowEngine or WorkflowRepository methods."""
        if self.workflow_engine:
            return self.workflow_engine.get_workflow_state(ctx.workflow_id)
        if self.workflow_repository:
            data = self.workflow_repository.get_workflow(ctx.workflow_id)
            if data is not None:
                agg, ver = data
                return agg.get("state", "initial"), ver
        return None

    def _validate_state_and_version(
        self,
        ctx: JobContext,
        legal_states: set[str | ProductVideoWorkflowState],
        inputs: dict[str, Any] | None = None,
        *,
        provider_family: str | None = None,
    ) -> JobFailed | None:
        missing_provider = (
            provider_family == "product_intelligence" and self._missing_pi_provider
        ) or (provider_family == "video_factory" and self._missing_video_provider)
        if missing_provider:
            details = getattr(self, "_missing_provider_details", None) or "live API provider adapters unconfigured"
            raise RuntimeError(
                f"MISSING_PROVIDER_CONFIG: {details} for provider_mode='configured'. "
                "Register the required MCP tools in config.yaml under 'mcp_servers' or set provider_mode='fake' for explicit offline/test verification."
            )

        res = self._get_workflow_state_and_version(ctx)
        if res is None:
            return JobFailed(
                retryable=False,
                code="WORKFLOW_NOT_FOUND",
                message=f"Workflow '{ctx.workflow_id}' not found in engine/repository",
            )

        current_state, current_version = res

        # 1. Reject if state is in HITL waiting states
        for hitl_st in HITL_WAITING_STATES:
            if current_state == hitl_st.value or current_state == hitl_st:
                return JobFailed(
                    retryable=False,
                    code="HITL_APPROVAL_REQUIRED",
                    message=f"Cannot dispatch job from HITL waiting state: {current_state}",
                )

        # 2. Reject if state is not legal for this job
        legal_state_values = {s.value if isinstance(s, ProductVideoWorkflowState) else str(s) for s in legal_states}
        if current_state not in legal_state_values:
            return JobFailed(
                retryable=False,
                code="ILLEGAL_WORKFLOW_STATE",
                message=f"State '{current_state}' is not legal for this stage. Allowed: {legal_state_values}",
            )

        # 3. Check version mismatch if expected_version is provided
        if ctx.expected_version is not None and ctx.expected_version != current_version:
            return JobFailed(
                retryable=False,
                code="VERSION_CONFLICT",
                message=f"Stale workflow version: expected {ctx.expected_version}, current {current_version}",
            )

        # 4. Check expected digests if provided
        if ctx.expected_digests and inputs:
            if not verify_job_digests(ctx.job_id, inputs, ctx.expected_digests):
                return JobFailed(
                    retryable=False,
                    code="DIGEST_MISMATCH",
                    message="Input digest verification failed",
                )

        return None

    def research_job(self, ctx: JobContext, product_name: str, keywords: list[str], pdp_url: str | None = None, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"product_name": product_name, "keywords": keywords}
        err = self._validate_state_and_version(
            ctx,
            {ProductVideoWorkflowState.RESEARCHING},
            inputs,
            provider_family="product_intelligence",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:research:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:research:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not product_name:
            return JobFailed(retryable=False, code="INVALID_INPUT", message="product_name cannot be empty")
        try:
            extra_kwargs = {
                key: kwargs[key]
                for key in ("brand", "model", "variant", "canonical_product_key", "research_snapshot_id")
                if kwargs.get(key) is not None
            }
            if pdp_url is not None:
                extra_kwargs["pdp_url"] = pdp_url
            result = self.pi_client.research(
                product_name,
                keywords,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_kwargs,
            )
            if pdp_url and not result.get("pdp_url"):
                result["pdp_url"] = pdp_url
            res = JobSucceeded(artifact_ref=result, next_command={"command": "build_resource_pack", "product_name": product_name})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as e:
            return JobFailed(retryable=False, code=e.code, message=str(e))
        except ValueError as e:
            return JobFailed(retryable=False, code="INVALID_INPUT", message=str(e))
        except Exception as e:
            return JobFailed(retryable=True, code="PI_RESEARCH_FAILED", message=str(e))

    def resource_pack_job(self, ctx: JobContext, research_result: dict, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"research_result": research_result}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
                ProductVideoWorkflowState.RESEARCHING,
            },
            inputs,
            provider_family="product_intelligence",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:resource_pack:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:resource_pack:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not research_result:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="research_result cannot be empty")

        # In configured provider_mode, validate research snapshot persistence prerequisite before dispatch
        if getattr(self, "provider_mode", "fake") == "configured":
            snapshot_id = research_result.get("snapshot_id")
            persistence_status = research_result.get("persistence_status")
            if not snapshot_id:
                return JobFailed(
                    retryable=False,
                    code="PREREQUISITE_FAILED",
                    message="Missing snapshot_id in research_result for configured mode",
                )
            if persistence_status not in ("saved", "persisted"):
                return JobFailed(
                    retryable=False,
                    code="PREREQUISITE_FAILED",
                    message=f"Research snapshot is not successfully persisted (persistence_status={persistence_status!r})",
                )

        try:
            result = self.pi_client.build_resource_pack(
                research_result,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            # Auto-run Image QC to check if cleanable failures exist
            # This is a preview QC run - not persisted yet, just for routing decision
            qc_result, qc_eligible = self._run_preview_image_qc(
                workflow_id=ctx.workflow_id,
                resource_pack=result,
                product_metadata=extract_product_from_resource_pack(result),
            )

            # Store QC metadata for retry handler
            result_with_qc = dict(result)
            result_with_qc["_initial_qc_preview"] = {
                "verdict": qc_result.verdict.value if hasattr(qc_result.verdict, 'value') else str(qc_result.verdict),
                "score": qc_result.score,
                "is_cleanable": is_cleanable_failure(qc_result),
                "findings_summary": {
                    "eligible_count": len(qc_eligible),
                    "total_items": len(qc_result.findings.get("items", [])),
                }
            }

            if qc_result.verdict == QCVerdict.FAIL and is_cleanable_failure(qc_result):
                # Cleanable failure - trigger auto-retry with image cleaning
                res = JobSucceeded(
                    artifact_ref=result_with_qc,
                    next_command={"command": "retry_image_qc"}
                )
            else:
                # Pass or terminal failure - proceed to normal flow
                res = JobSucceeded(
                    artifact_ref=result_with_qc,
                    next_command={"command": "lock_resource_pack"}
                )

            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as e:
            return JobFailed(retryable=False, code=e.code, message=str(e))
        except ValueError as e:
            return JobFailed(retryable=False, code="PREREQUISITE_FAILED", message=str(e))
        except Exception as e:
            return JobFailed(retryable=True, code="PI_PACK_FAILED", message=str(e))

    def lock_job(self, ctx: JobContext, pack_dict: dict, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"pack_dict": pack_dict}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.LOCKING_RESOURCE_PACK,
                ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
                ProductVideoWorkflowState.RETRYING_IMAGE_QC,
            },
            inputs,
            provider_family="product_intelligence",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:lock:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:lock:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not pack_dict:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="pack_dict cannot be empty")

        resource_pack_id = pack_dict.get("resource_pack_id") or pack_dict.get("id") or pack_dict.get("pack_id")
        if not resource_pack_id:
            if getattr(self, "provider_mode", "fake") == "fake":
                resource_pack_id = f"pack_{ctx.workflow_id}"
            else:
                return JobFailed(
                    retryable=False,
                    code="PREREQUISITE_FAILED",
                    message="Cannot lock resource pack: missing resource_pack_id in pack_dict",
                )

        pack_status = pack_dict.get("pack_status") or pack_dict.get("status")
        if pack_status in ("needs_review", "incomplete", "rejected", "unknown") or (getattr(self, "provider_mode", "fake") == "configured" and pack_status != "ready_to_lock"):
            return JobFailed(
                retryable=False,
                code="NON_LOCKABLE_STATUS",
                message=f"Cannot lock resource pack with non-lockable status '{pack_status}': pack is not ready_to_lock",
            )

        proj_id = kwargs.get("project_id")
        if not proj_id and self.workflow_repository:
            try:
                wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                if wf_d:
                    proj_id = wf_d[0].get("project_id")
            except Exception:
                pass
        if not proj_id:
            proj_id = f"proj_{ctx.workflow_id}"

        try:
            result = self.pi_client.lock_resource_pack(
                pack_dict,
                ctx.owner_user_id,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                project_id=proj_id,
            )
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_creative_brief"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as e:
            return JobFailed(retryable=False, code=e.code, message=str(e))
        except ValueError as e:
            return JobFailed(retryable=False, code="PREREQUISITE_FAILED", message=str(e))
        except Exception as e:
            return JobFailed(retryable=True, code="PI_LOCK_FAILED", message=str(e))

    def creative_brief_job(self, ctx: JobContext, product_id: str, brief_config: dict | None = None, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"product_id": product_id, "brief_config": brief_config or {}}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.CREATING_BRIEF,
                ProductVideoWorkflowState.LOCKING_RESOURCE_PACK,
                ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:creative_brief:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:creative_brief:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not product_id:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="product_id cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget(
                "video_factory",
                5,
                idempotency_key=cache_key,
                **_paid_budget_kwargs(ctx, "product_video.creative_brief", kwargs, cache_key),
            )
            proj_id = (brief_config or {}).get("project_id") or kwargs.get("project_id")
            if not proj_id and self.workflow_repository:
                try:
                    wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                    if wf_d:
                        proj_id = wf_d[0].get("project_id")
                except Exception:
                    pass
            if not proj_id:
                proj_id = f"proj_{ctx.workflow_id}"

            cfg = dict(brief_config or {})
            cfg.setdefault("project_id", proj_id)

            if self.creative_generator is not None:
                dossier_data = cfg.get("research_dossier")
                if self.workflow_repository is not None:
                    from hermes_personal.product_video.creative.generator import SingleModelCreativeGenerator

                    if isinstance(self.creative_generator, SingleModelCreativeGenerator):
                        workflow_data = self.workflow_repository.get_workflow(ctx.workflow_id)
                        if workflow_data is not None:
                            aggregate, _ = workflow_data
                            locked_pack = aggregate.get("locked_pack")
                            if isinstance(locked_pack, dict):
                                # The queued brief job may contain a dossier
                                # built before the approved lock was mirrored.
                                # Rebuild from the durable lock and current
                                # passing QC instead of trusting that stale copy.
                                dossier_data = _locked_research_dossier(
                                    workflow_id=ctx.workflow_id,
                                    aggregate=aggregate,
                                    locked_pack=locked_pack,
                                    connection=self.workflow_repository.conn,
                                )
                                cfg["research_dossier"] = dossier_data
                dossier = None
                if dossier_data:
                    from hermes_personal.product_video.creative.contracts import ResearchDossier
                    dossier = ResearchDossier.from_dict(dossier_data) if isinstance(dossier_data, dict) else dossier_data
                if dossier is None:
                    dossier = getattr(self.creative_generator, "dossier", None)
                if dossier is not None:
                    recovered_brief = None
                    if isinstance(self.video_client, MCPVideoFactoryAdapter):
                        workflow_data = self.workflow_repository.get_workflow(ctx.workflow_id) if self.workflow_repository else None
                        if workflow_data is None:
                            raise ValueError("workflow state is required to synchronize the approved Product Lock")
                        aggregate, _ = workflow_data
                        locked_pack = aggregate.get("locked_pack")
                        approval_receipt = aggregate.get("latest_approval_receipt")
                        if not isinstance(locked_pack, dict) or not isinstance(approval_receipt, dict):
                            raise ValueError("approved Product Lock artifact and receipt are required before creative generation")
                        dossier_dict = dossier.to_dict() if hasattr(dossier, "to_dict") else dossier
                        if not isinstance(dossier_dict, dict):
                            raise ValueError("grounded dossier must be serializable")
                        self.video_client.ensure_project_locked(
                            owner_user_id=ctx.owner_user_id,
                            project_id=proj_id,
                            resource_pack=locked_pack,
                            dossier=dossier_dict,
                            approval_receipt=approval_receipt,
                            workflow_id=ctx.workflow_id,
                            # This downstream mirror is created after the
                            # approval transition, so the current workflow
                            # version is newer than the approved artifact.
                            workflow_version=None,
                        )
                        recovered_brief = _recover_creative_brief(
                            self.video_client.get_existing_creative_brief(
                                owner_user_id=ctx.owner_user_id,
                                project_id=proj_id,
                            ) or {},
                            dossier,
                        )
                    brief_v2 = recovered_brief or self.creative_generator.create_direction(dossier)
                    sent_config = _video_factory_brief_config(dict(cfg), brief_v2)
                    result = (
                        {"project_id": proj_id, "brief_id": f"brief_{product_id}"}
                        if recovered_brief is not None
                        else self.video_client.create_creative_brief(
                            product_id=product_id,
                            brief_config=sent_config,
                            workflow_id=ctx.workflow_id,
                            job_id=ctx.job_id,
                            project_id=proj_id,
                            owner_user_id=ctx.owner_user_id,
                            idempotency_key=ctx.idempotency_key,
                        )
                    )
                    res_dict = dict(brief_v2.to_dict())
                    res_dict["schema_version"] = "creative-brief-v2"
                    res_dict["contract_version"] = 2
                    res_dict["brief_digest"] = brief_v2.digest()
                    res_dict["project_id"] = proj_id
                    res_dict["research_dossier"] = dossier.to_dict() if hasattr(dossier, "to_dict") else dossier_data
                    if isinstance(result, dict):
                        if "version" in result:
                            res_dict["version"] = result["version"]
                        if "brief_id" in result:
                            res_dict["brief_id"] = result["brief_id"]
                    commit_budget(alloc)
                    res = JobSucceeded(artifact_ref=res_dict, next_command={"command": "create_scene_plan", "product_id": product_id})
                    if cache_key:
                        self._idempotency_cache[cache_key] = res
                    return res

            extra_brief_kw: dict[str, Any] = {}
            if kwargs.get("project_id"):
                extra_brief_kw["project_id"] = kwargs["project_id"]
            if kwargs.get("owner_user_id"):
                extra_brief_kw["owner_user_id"] = kwargs["owner_user_id"]

            result = self.video_client.create_creative_brief(
                product_id=product_id,
                brief_config=cfg,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_brief_kw,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_scene_plan", "product_id": product_id})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_BRIEF_FAILED", message=str(e))

    def scene_plan_job(self, ctx: JobContext, brief_ref: Any, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"brief_ref": brief_ref}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.CREATING_SCENE_PLAN,
                ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:scene_plan:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:scene_plan:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not brief_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="brief_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget(
                "video_factory",
                5,
                idempotency_key=cache_key,
                **_paid_budget_kwargs(ctx, "product_video.scene_plan", kwargs, cache_key),
            )
            proj_id = kwargs.get("project_id")
            if not proj_id and isinstance(brief_ref, dict):
                proj_id = brief_ref.get("project_id")
            if not proj_id and self.workflow_repository:
                try:
                    wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                    if wf_d:
                        proj_id = wf_d[0].get("project_id")
                except Exception:
                    pass
            if not proj_id:
                proj_id = f"proj_{ctx.workflow_id}"

            if self.creative_generator is not None:
                brief_dict = brief_ref if isinstance(brief_ref, dict) else {}
                dossier_dict = brief_dict.get("research_dossier")
                from hermes_personal.product_video.creative.contracts import (
                    CreativeBriefV2, ResearchDossier, ScriptScenePlanV2,
                )
                dossier = getattr(self.creative_generator, "dossier", None)
                if dossier is None and dossier_dict:
                    dossier = ResearchDossier.from_dict(dossier_dict)
                brief_v2 = getattr(self.creative_generator, "brief", None)
                if brief_v2 is None and brief_dict:
                    try:
                        brief_v2 = CreativeBriefV2.from_dict(brief_dict)
                    except Exception:
                        pass
                if dossier and brief_v2:
                    script_v2 = self.creative_generator.create_script(dossier, brief_v2)
                    legacy_scenes = [
                        {
                            "scene_id": s.scene_id,
                            "order": s.order,
                            "title": f"Scene {s.order}: {s.story_role}",
                            "objective": s.visual_objective,
                            "content": s.narration,
                            "main_action": s.subject_action,
                            "duration_seconds": s.duration_seconds,
                            "start_state": s.start_state,
                            "end_state": s.end_state,
                            "camera_intention": s.camera_movement,
                        }
                        for s in script_v2.scenes
                    ]
                    sent_brief = dict(brief_dict)
                    sent_brief["scenes"] = legacy_scenes
                    sent_brief.setdefault("project_id", proj_id)
                    appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")
                    result = self.video_client.create_scene_plan(
                        sent_brief,
                        workflow_id=ctx.workflow_id,
                        job_id=ctx.job_id,
                        project_id=proj_id,
                        owner_user_id=ctx.owner_user_id,
                        idempotency_key=ctx.idempotency_key,
                        approval_request_id=appr_id,
                        approval_receipt=kwargs.get("approval_receipt"),
                    )
                    res_dict = dict(script_v2.to_dict())
                    res_dict["schema_version"] = "script-scene-plan-v2"
                    # Hash the exact serialized payload handed to the next
                    # worker. A digest of the in-memory object can diverge if
                    # its nested scene data was normalized during generation.
                    res_dict["script_digest"] = ScriptScenePlanV2.from_dict(
                        {**res_dict, "script_digest": ""}
                    ).digest()
                    res_dict["project_id"] = proj_id
                    res_dict["research_dossier"] = dossier.to_dict() if hasattr(dossier, "to_dict") else dossier_dict
                    if isinstance(result, dict) and "scene_plan_id" in result:
                        res_dict["scene_plan_id"] = result["scene_plan_id"]
                    commit_budget(alloc)
                    res = JobSucceeded(artifact_ref=res_dict, next_command={"command": "create_storyboard"})
                    if cache_key:
                        self._idempotency_cache[cache_key] = res
                    return res

            extra_scene_kw: dict[str, Any] = {}
            if kwargs.get("project_id"):
                extra_scene_kw["project_id"] = kwargs["project_id"]
            if kwargs.get("owner_user_id"):
                extra_scene_kw["owner_user_id"] = kwargs["owner_user_id"]
            if kwargs.get("approval_request_id"):
                extra_scene_kw["approval_request_id"] = kwargs["approval_request_id"]
            if kwargs.get("approval_receipt"):
                extra_scene_kw["approval_receipt"] = kwargs["approval_receipt"]

            result = self.video_client.create_scene_plan(
                brief_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_scene_kw,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_storyboard"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=True, code="VF_SCENE_FAILED", message=str(e))


    def storyboard_job(self, ctx: JobContext, scene_ref: Any, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"scene_ref": scene_ref}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.CREATING_STORYBOARD,
                ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:storyboard:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:storyboard:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not scene_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="scene_ref cannot be empty")
        if self.workflow_repository:
            workflow_data = self.workflow_repository.get_workflow(ctx.workflow_id)
            if workflow_data is not None and isinstance(workflow_data[0].get("qc_authorization"), dict):
                kwargs = dict(kwargs)
                kwargs["qc_authorization"] = dict(workflow_data[0]["qc_authorization"])
        alloc = None
        try:
            alloc = reserve_budget(
                "video_factory",
                10,
                idempotency_key=cache_key,
                **_paid_budget_kwargs(ctx, "product_video.storyboard", kwargs, cache_key),
            )
            proj_id = kwargs.get("project_id")
            if not proj_id and isinstance(scene_ref, dict):
                proj_id = scene_ref.get("project_id")
            if not proj_id and self.workflow_repository:
                try:
                    wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                    if wf_d:
                        proj_id = wf_d[0].get("project_id")
                except Exception:
                    pass
            if not proj_id:
                proj_id = f"proj_{ctx.workflow_id}"

            appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")

            if self.keyframe_runtime_factory is not None:
                runtime = self.keyframe_runtime_factory()
                from hermes_personal.product_video.creative.contracts import ResearchDossier, ScriptScenePlanV2
                from hermes_personal.product_video.creative.storyboard import (
                    compile_keyframe_requests,
                    storyboard_package_digest,
                )
                dossier = getattr(self.creative_generator, "dossier", None)
                if dossier is None and isinstance(scene_ref, dict) and "research_dossier" in scene_ref:
                    dossier = ResearchDossier.from_dict(scene_ref["research_dossier"])
                if dossier and isinstance(scene_ref, dict):
                    eligible_ids = [asset.asset_id for asset in dossier.eligible_assets]
                    for scene in scene_ref.get("scenes", []) or []:
                        if isinstance(scene, dict) and not scene.get("reference_asset_ids"):
                            scene["reference_asset_ids"] = eligible_ids[:2]
                script = getattr(self.creative_generator, "script", None)
                if script is None and isinstance(scene_ref, dict):
                    try:
                        script = ScriptScenePlanV2.from_dict(scene_ref)
                    except (KeyError, TypeError, ValueError) as exc:
                        if scene_ref.get("schema_version") == "script-scene-plan-v2":
                            release_budget(alloc)
                            return JobFailed(
                                retryable=False, code="INVALID_SCRIPT_DIGEST",
                                message=f"Stored V2 scene plan failed validation: {exc}",
                            )
                if dossier and script:
                    vf_storyboard = self.video_client.create_storyboard(
                        scene_ref,
                        workflow_id=ctx.workflow_id,
                        job_id=ctx.job_id,
                        project_id=proj_id,
                        owner_user_id=ctx.owner_user_id,
                        idempotency_key=ctx.idempotency_key,
                        approval_request_id=appr_id,
                        approval_receipt=kwargs.get("approval_receipt"),
                    )
                    _confirm_vf_storyboard_write(
                        vf_storyboard,
                        owner_user_id=ctx.owner_user_id,
                        project_id=proj_id,
                        scene_ids=tuple(scene.scene_id for scene in script.scenes),
                    )
                    requests = compile_keyframe_requests(
                        workflow_id=ctx.workflow_id,
                        project_id=proj_id,
                        dossier=dossier,
                        script=script,
                        recovery_plan=(
                            kwargs.get("recovery_plan")
                            if isinstance(kwargs.get("recovery_plan"), dict)
                            else None
                        ),
                        recovery_attempt=int(kwargs.get("recovery_attempt", 0) or 0),
                        previous_package=(
                            kwargs.get("previous_storyboard")
                            if isinstance(kwargs.get("previous_storyboard"), dict)
                            else None
                        ),
                    )
                    previous_package = kwargs.get("previous_storyboard")
                    recovery_plan = kwargs.get("recovery_plan")
                    recovery_frame_ids = {
                        str(item.get("frame_id"))
                        for item in (recovery_plan or {}).get("frames", [])
                        if isinstance(item, dict) and item.get("frame_id")
                    } if isinstance(recovery_plan, dict) else set()
                    previous_frames: dict[str, dict[str, Any]] = {}
                    unchanged_scene_ids: set[str] = set()
                    if isinstance(previous_package, dict) and (
                        previous_package.get("workflow_id") == ctx.workflow_id
                        and previous_package.get("project_id") == proj_id
                        and previous_package.get("package_digest") == storyboard_package_digest(previous_package)
                        and isinstance(previous_package.get("script"), dict)
                    ):
                        old_script = ScriptScenePlanV2.from_dict(previous_package["script"])
                        old_scenes = {scene.scene_id: scene for scene in old_script.scenes}
                        unchanged_scene_ids = {
                            scene.scene_id for scene in script.scenes
                            if old_scenes.get(scene.scene_id) == scene
                        }
                        previous_frames = {
                            str(item["frame_id"]): item
                            for item in previous_package.get("generated_keyframes", [])
                            if isinstance(item, dict) and item.get("frame_id")
                        }
                    generated_keyframes = []
                    for req in requests:
                        prior = previous_frames.get(req.frame_id)
                        scene_id = req.frame_id.removesuffix("-start").removesuffix("-end")
                        if prior is not None and scene_id in unchanged_scene_ids and req.frame_id not in recovery_frame_ids:
                            prior_path = Path(str(prior.get("image_path") or ""))
                            if (
                                prior.get("status") == "completed"
                                and prior_path.is_file()
                                and hashlib.sha256(prior_path.read_bytes()).hexdigest() == prior.get("sha256")
                            ):
                                generated_keyframes.append(dict(prior))
                                continue
                        conditioning_start_sha = ""
                        if req.frame_role == "end":
                            start_frame = next(
                                (
                                    item for item in generated_keyframes
                                    if item.get("frame_id") == f"{scene_id}-start"
                                ),
                                None,
                            )
                            if not isinstance(start_frame, dict):
                                raise ValueError("END keyframe requires its completed START frame")
                            start_path = Path(str(start_frame.get("image_path") or ""))
                            conditioning_start_sha = str(start_frame.get("sha256") or "")
                            if (
                                not start_path.is_file()
                                or hashlib.sha256(start_path.read_bytes()).hexdigest() != conditioning_start_sha
                            ):
                                raise ValueError("END keyframe START conditioning image changed")
                            req = replace(
                                req,
                                prompt=(
                                    req.prompt
                                    + "\nThe first attached image is the approved START frame of this same scene. "
                                    "Keep its exact table material, shape, furniture layout, camera context, "
                                    "product surface and pool position. Show only the specified action and end state. "
                                    "If water is specified near but not on the product, keep the product completely dry."
                                ),
                                reference_image_paths=(str(start_path), *req.reference_image_paths)[:4],
                            )
                        if ctx.heartbeat_fn is not None and not ctx.heartbeat_fn():
                            release_budget(alloc)
                            return JobFailed(retryable=True, code="STALE_LEASE", message="Storyboard lease expired before keyframe generation")
                        kf_res = runtime.run(req)
                        if kf_res.status != "completed" or not kf_res.image_path:
                            release_budget(alloc)
                            if kf_res.error_code == "PROVIDER_CAPACITY_WAIT":
                                return JobFailed(
                                    retryable=True, code="PROVIDER_CAPACITY_WAIT",
                                    message=kf_res.error_message or "Keyframe provider is at capacity",
                                )
                            if str(kf_res.error_code or "").upper() in {
                                "HTTP_429", "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504",
                            }:
                                return JobFailed(
                                    retryable=True, code="PROVIDER_CAPACITY_WAIT",
                                    message=kf_res.error_message or (
                                        f"Keyframe provider returned {kf_res.error_code}; retry later"
                                    ),
                                )
                            if kf_res.status in {"submitted", "running"} and kf_res.provider_operation_id:
                                return JobFailed(
                                    retryable=True, code="KEYFRAME_PENDING",
                                    message="Keyframe operation is pending under its existing provider ID",
                                )
                            return JobFailed(
                                retryable=False,
                                code=kf_res.error_code or "RECONCILIATION_REQUIRED",
                                message=kf_res.error_message or "Keyframe operation did not complete",
                            )
                        ref_shas = [
                            hashlib.sha256(Path(path).read_bytes()).hexdigest()
                            for path in req.reference_image_paths
                        ]
                        scene_id = req.frame_id.removesuffix("-start").removesuffix("-end")
                        kf_p = Path(kf_res.image_path) if kf_res.image_path else None
                        kf_sha = hashlib.sha256(kf_p.read_bytes()).hexdigest() if (kf_p and kf_p.is_file()) else ""
                        generated_keyframes.append({
                            "frame_id": req.frame_id,
                            "scene_id": scene_id,
                            "frame_role": req.frame_role,
                            "image_path": kf_res.image_path,
                            "sha256": kf_sha,
                            "status": kf_res.status,
                            "prompt": req.prompt,
                            "negative_prompt": req.negative_prompt,
                            "reference_image_paths": list(req.reference_image_paths),
                            "reference_sha256s": ref_shas,
                            "conditioning_start_sha256": conditioning_start_sha,
                        })
                    package_dict = {
                        "schema_version": "storyboard-package-v2",
                        "storyboard_id": f"sb_{proj_id}",
                        "version": 1,
                        "owner_user_id": ctx.owner_user_id,
                        "generated_keyframes": generated_keyframes,
                        "storyboard_frames": [
                            {
                                "scene_id": scene.scene_id,
                                "keyframe_image_path": next(
                                    (
                                        item["image_path"]
                                        for item in generated_keyframes
                                        if item["scene_id"] == scene.scene_id
                                        and item["frame_role"] == "start"
                                    ),
                                    None,
                                ),
                                "reference_image_paths": list(
                                    next(
                                        (
                                            req.reference_image_paths
                                            for req in requests
                                            if req.frame_id == f"{scene.scene_id}-start"
                                        ),
                                        (),
                                    )
                                ),
                                "visual_objective": scene.visual_objective,
                                "overlay_text": scene.overlay_text,
                                "text_policy": "post_production_only",
                            }
                            for scene in script.scenes
                        ],
                        "project_id": proj_id,
                        "workflow_id": ctx.workflow_id,
                        "script": script.to_dict() if hasattr(script, "to_dict") else (asdict(script) if is_dataclass(script) else script),
                        "scenes": [s.to_dict() if hasattr(s, "to_dict") else (asdict(s) if is_dataclass(s) else s) for s in script.scenes],
                        "recovery_attempt": int(kwargs.get("recovery_attempt", 0) or 0),
                        "end_keyframe_omissions": [
                            {
                                "scene_id": s.scene_id,
                                "policy": s.end_keyframe_policy,
                                "reason": s.end_keyframe_omission_reason,
                            }
                            for s in script.scenes
                            if s.end_keyframe_policy == "omitted"
                        ],
                    }
                    package_dict["package_digest"] = storyboard_package_digest(package_dict)
                    commit_budget(alloc)
                    res = JobSucceeded(artifact_ref=package_dict, next_command={"command": "render_video"})
                    if cache_key:
                        self._idempotency_cache[cache_key] = res
                    return res

            extra_sb_kw: dict[str, Any] = {}
            if kwargs.get("project_id"):
                extra_sb_kw["project_id"] = kwargs["project_id"]
            if kwargs.get("owner_user_id"):
                extra_sb_kw["owner_user_id"] = kwargs["owner_user_id"]
            if appr_id:
                extra_sb_kw["approval_request_id"] = appr_id
            if isinstance(kwargs.get("approval_receipt"), dict):
                extra_sb_kw["approval_receipt"] = kwargs["approval_receipt"]

            result = self.video_client.create_storyboard(
                scene_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_sb_kw,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "render_video"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_STORYBOARD_FAILED", message=str(e))

    def render_job(self, ctx: JobContext, story_ref: Any, render_params: dict | None = None, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"story_ref": story_ref}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.RENDERING,
                ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err
        if not story_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="story_ref cannot be empty")

        params = dict(render_params or {})
        wf_data = self.workflow_repository.get_workflow(ctx.workflow_id) if self.workflow_repository else None
        agg = wf_data[0] if wf_data else {}
        cur_ver = wf_data[1] if wf_data else 1
        try:
            active_job_id = _resolve_durable_resume_job_id(
                params,
                agg,
                "active_render_job_id",
                ("job_id", "export_id"),
            )
        except TerminalJobError as exc:
            return JobFailed(retryable=False, code=exc.code, message=str(exc))

        cache_key = f"{ctx.workflow_id}:render:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:render:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        disp_status = agg.get("render_dispatch_status")
        if disp_status in ("DISPATCHING", "UNKNOWN_OUTCOME"):
            return JobFailed(retryable=False, code="UNKNOWN_PAID_OUTCOME", message=f"Cannot resume from unconfirmed dispatch status '{disp_status}'")
        if disp_status == "COMPLETED":
            res_id = agg.get("render_budget_reservation_id")
            if not res_id or res_id == "absent":
                return JobFailed(retryable=False, code="BUDGET_RECOVERY_FAILED", message="Completed render missing valid budget reservation")
            res_obj = get_reservation(res_id)
            if not res_obj:
                return JobFailed(retryable=False, code="BUDGET_RECOVERY_FAILED", message=f"Reservation '{res_id}' not found")
            commit_budget(res_obj)
            return JobSucceeded(artifact_ref=agg.get("render_result", {}), next_command={"command": "export_video"})

        if getattr(self, "provider_mode", "fake") == "configured" and not active_job_id:
            try:
                _require_configured_execution_binding(
                    self.video_client,
                    "render",
                    "video.render",
                )
            except TerminalJobError as exc:
                return JobFailed(
                    retryable=False,
                    code=exc.code,
                    message=str(exc),
                )
            except ExecutionBindingPreflightError as exc:
                return JobFailed(
                    retryable=exc.retryable,
                    code=exc.code,
                    message=str(exc),
                )
            qc_auth = kwargs.get("qc_authorization") or params.get("qc_authorization") or agg.get("qc_authorization")
            if not qc_auth or not isinstance(qc_auth, dict):
                return JobFailed(retryable=False, code="COST_AUTHORIZATION_REQUIRED", message="Configured render requires scoped qc_authorization")
            max_cost = qc_auth.get("max_cost_usd", qc_auth.get("workflow_max_cost_usd"))
            if max_cost is None or float(max_cost) < 0.50:
                return JobFailed(retryable=False, code="COST_AUTHORIZATION_REQUIRED", message=f"Authorization max_cost_usd {max_cost} is below durable admission threshold (0.50)")

        def _checkpoint_accepted(job_type: str, prov_job_id: str) -> None:
            if not self.workflow_repository or not ctx.workflow_id:
                return
            try:
                data = self.workflow_repository.get_workflow(ctx.workflow_id)
                if not data:
                    raise RuntimeError(f"Workflow '{ctx.workflow_id}' not found during checkpoint")
                agg_data, ver = data
                agg_dict = dict(agg_data)
                agg_dict["active_render_job_id"] = prov_job_id
                if alloc:
                    agg_dict["render_budget_reservation_id"] = alloc.reservation_id
                self.workflow_repository.commit_workflow(
                    workflow_id=ctx.workflow_id,
                    aggregate_json=json.dumps(agg_dict),
                    events=[],
                    expected_version=ver,
                )
            except Exception as ex:
                raise TerminalJobError(
                    f"CHECKPOINT_PERSISTENCE_FAILED: Failed to checkpoint accepted provider job_id '{prov_job_id}' in workflow repository: {ex}. "
                    "Auto-resubmission halted to prevent duplicate provider job submission.",
                    code="VF_CHECKPOINT_FAILED",
                ) from ex

        alloc = None
        provider_call_started = False
        try:
            proj_id = kwargs.get("project_id") or agg.get("project_id") or f"proj_{ctx.workflow_id}"
            if not active_job_id:
                alloc = reserve_budget(
                    "video_factory",
                    50,
                    idempotency_key=cache_key,
                    **_paid_budget_kwargs(ctx, "product_video.render", kwargs, cache_key),
                )
                params["admission_context"] = {
                    "reservation_id": alloc.reservation_id,
                    "budget_reservation_id": alloc.reservation_id,
                    "workflow_id": ctx.workflow_id,
                }
            elif agg.get("render_budget_reservation_id"):
                alloc = get_reservation(agg["render_budget_reservation_id"])
                if alloc is None or alloc.state == "released":
                    return JobFailed(
                        retryable=False, code="BUDGET_RECOVERY_FAILED",
                        message="Accepted render budget reservation is missing or released",
                    )
            appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")
            story_dict = dict(story_ref) if isinstance(story_ref, dict) else {}
            if story_dict.get("schema_version") == "storyboard-package-v2":
                curr_rcpt = story_dict.get("keyframe_qc_receipt")
                if not isinstance(curr_rcpt, dict) or curr_rcpt.get("artifact_digest") != story_dict.get("package_digest"):
                    qc_repo = QCReportRepository(self.workflow_repository.conn)
                    latest_qc = qc_repo.get_latest_report(ctx.workflow_id, QCStage.KEYFRAME)
                    if latest_qc and getattr(latest_qc.verdict, "value", str(latest_qc.verdict)).lower() == "pass":
                        story_dict["keyframe_qc_receipt"] = {
                            "report_id": latest_qc.report_id,
                            "workflow_id": latest_qc.workflow_id,
                            "stage": getattr(latest_qc.stage, "value", str(latest_qc.stage)),
                            "verdict": getattr(latest_qc.verdict, "value", str(latest_qc.verdict)),
                            "score": latest_qc.score,
                            "artifact_id": latest_qc.artifact_id,
                            "artifact_version": latest_qc.artifact_version,
                            "artifact_digest": latest_qc.artifact_digest,
                            "findings": latest_qc.findings,
                            "hard_failure": getattr(latest_qc, "hard_failure", False),
                        }
                    elif not curr_rcpt:
                        story_dict["keyframe_qc_receipt"] = kwargs.get("approval_receipt") or {
                            "approval_request_id": appr_id or "appr_auto",
                            "gate": "AwaitingStoryboardApproval",
                            "status": "approved",
                        }
            provider_call_started = True
            result = self.video_client.render_video(
                story_dict,
                render_params=params,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                on_job_accepted=_checkpoint_accepted,
                heartbeat_fn=ctx.heartbeat_fn,
                owner_user_id=ctx.owner_user_id,
                project_id=proj_id,
                approval_request_id=appr_id,
            )

            if alloc:
                commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "export_video"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as te:
            uncertain_paid_codes = {
                "RECONCILIATION_REQUIRED",
                "VF_CHECKPOINT_FAILED",
                "MISSING_JOB_ID",
                "MISSING_POLLING_TOOL",
                "RENDER_LINEAGE_INVALID",
                "RENDER_LINEAGE_MISMATCH",
            }
            if alloc and not (
                provider_call_started
                and self.provider_mode == "configured"
                and te.code in uncertain_paid_codes
            ):
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=False, code=te.code, message=str(te))
        except LeaseLostError as le:
            if alloc and not (provider_call_started and self.provider_mode == "configured"):
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=False, code="LEASE_LOST", message=str(le))
        except Exception as e:
            if provider_call_started and self.provider_mode == "configured":
                durable_job = None
                if self.workflow_repository:
                    try:
                        resumed = self.workflow_repository.get_workflow(ctx.workflow_id)
                        durable_job = resumed[0].get("active_render_job_id") if resumed else None
                    except Exception:
                        durable_job = None
                if not durable_job:
                    return JobFailed(
                        retryable=False, code="UNKNOWN_PAID_OUTCOME",
                        message=f"Render outcome is ambiguous; reconcile the provider before retrying: {e}",
                    )
                return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))

    def export_job(self, ctx: JobContext, render_ref: Any, export_params: dict | None = None, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"render_ref": render_ref}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.EXPORTING,
                ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err
        if not render_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="render_ref cannot be empty")

        params = dict(export_params or {})
        wf_data = self.workflow_repository.get_workflow(ctx.workflow_id) if self.workflow_repository else None
        agg = wf_data[0] if wf_data else {}
        cur_ver = wf_data[1] if wf_data else 1
        try:
            active_job_id = _resolve_durable_resume_job_id(
                params,
                agg,
                "active_export_job_id",
                ("job_id", "export_id"),
            )
        except TerminalJobError as exc:
            return JobFailed(retryable=False, code=exc.code, message=str(exc))

        cache_key = f"{ctx.workflow_id}:export:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:export:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        disp_status = agg.get("export_dispatch_status")
        if disp_status in ("DISPATCHING", "UNKNOWN_OUTCOME"):
            return JobFailed(retryable=False, code="UNKNOWN_PAID_OUTCOME", message=f"Cannot resume from unconfirmed dispatch status '{disp_status}'")
        if disp_status == "COMPLETED":
            res_id = agg.get("export_budget_reservation_id")
            if not res_id or res_id == "absent":
                return JobFailed(retryable=False, code="BUDGET_RECOVERY_FAILED", message="Completed export missing valid budget reservation")
            res_obj = get_reservation(res_id)
            if not res_obj:
                return JobFailed(retryable=False, code="BUDGET_RECOVERY_FAILED", message=f"Reservation '{res_id}' not found")
            commit_budget(res_obj)
            return JobSucceeded(artifact_ref=agg.get("export_result", {}), next_command={"command": "complete"})

        def _checkpoint_accepted(job_type: str, prov_job_id: str) -> None:
            if not self.workflow_repository or not ctx.workflow_id:
                return
            try:
                data = self.workflow_repository.get_workflow(ctx.workflow_id)
                if not data:
                    raise RuntimeError(f"Workflow '{ctx.workflow_id}' not found during checkpoint")
                agg_data, ver = data
                agg_dict = dict(agg_data)
                agg_dict["active_export_job_id"] = prov_job_id
                self.workflow_repository.commit_workflow(
                    workflow_id=ctx.workflow_id,
                    aggregate_json=json.dumps(agg_dict),
                    events=[],
                    expected_version=ver,
                )
            except Exception as ex:
                raise TerminalJobError(
                    f"CHECKPOINT_PERSISTENCE_FAILED: Failed to checkpoint accepted provider job_id '{prov_job_id}' in workflow repository: {ex}. "
                    "Auto-resubmission halted to prevent duplicate provider job submission.",
                    code="VF_CHECKPOINT_FAILED",
                ) from ex

        alloc = None
        try:
            proj_id = kwargs.get("project_id") or agg.get("project_id") or f"proj_{ctx.workflow_id}"
            appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")
            if getattr(self, "provider_mode", "fake") == "configured" and not active_job_id:
                try:
                    _require_configured_execution_binding(
                        self.video_client,
                        "export",
                        "video.export",
                    )
                except TerminalJobError as exc:
                    return JobFailed(
                        retryable=False,
                        code=exc.code,
                        message=str(exc),
                    )
                except ExecutionBindingPreflightError as exc:
                    return JobFailed(
                        retryable=exc.retryable,
                        code=exc.code,
                        message=str(exc),
                    )
            if not active_job_id:
                alloc = reserve_budget(
                    "video_factory",
                    20,
                    idempotency_key=cache_key,
                    **_paid_budget_kwargs(ctx, "product_video.export", kwargs, cache_key),
                )
            result = self.video_client.export_video(
                render_ref,
                export_params=params,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                on_job_accepted=_checkpoint_accepted,
                heartbeat_fn=ctx.heartbeat_fn,
                owner_user_id=ctx.owner_user_id,
                project_id=proj_id,
                approval_request_id=appr_id,
            )

            if alloc:
                commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "complete"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as te:
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=False, code=te.code, message=str(te))
        except LeaseLostError as le:
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=False, code="LEASE_LOST", message=str(le))
        except Exception as e:
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=True, code="VF_EXPORT_FAILED", message=str(e))


    def get_handlers_map(self) -> dict[str, Callable[..., Any]]:
        return {
            "product_video.research": self.research_job,
            "product_video.resource_pack": self.resource_pack_job,
            "product_video.retry_image_qc": self.retry_image_qc_job,
            "product_video.lock": self.lock_job,
            "product_video.creative_brief": self.creative_brief_job,
            "product_video.scene_plan": self.scene_plan_job,
            "product_video.storyboard": self.storyboard_job,
            "product_video.render": self.render_job,
            "product_video.export": self.export_job,
        }

    def __len__(self) -> int:
        return len(self.get_handlers_map())

    def __getitem__(self, item: str) -> Callable[..., Any]:
        return self.get_handlers_map()[item]

    def __contains__(self, item: str) -> bool:
        return item in self.get_handlers_map()

    def dispatch_registered_job(self, job_name: str, ctx: JobContext, *args: Any, **kwargs: Any) -> JobResult:
        """Create a Gate 4 JobSpec and dispatch it through JobDispatcher."""
        handlers = self.get_handlers_map()
        if job_name not in handlers:
            raise ValueError(f"Unknown job handler: {job_name}")
        handler_fn = handlers[job_name]
        spec = JobSpec(
            job_id=ctx.job_id,
            func=handler_fn,
            args=(ctx, *args),
            kwargs=kwargs,
        )
        if not self.dispatcher:
            raise RuntimeError("No JobDispatcher attached to ProductVideoJobHandlers")
        return self.dispatcher.dispatch(spec)

    def wait_for_job(self, job_id: str, timeout: float = 2.0) -> JobResult | None:
        """Wait for a dispatched job to reach terminal state."""
        if not self.dispatcher:
            return None
        start = time.time()
        while time.time() - start < timeout:
            res = self.dispatcher.get_result(job_id)
            if res and res.status in (JobStatus.SUCCESS, JobStatus.FAILURE):
                return res
            time.sleep(0.01)
        return self.dispatcher.get_result(job_id)


def register_product_video_job_handlers(
    dispatcher: JobDispatcher | Any,
    handlers_service: ProductVideoJobHandlers | None = None,
    workflow_engine: WorkflowEngine | None = None,
    pi_client: ProductIntelligenceClient | None = None,
    video_client: VideoFactoryClient | None = None,
    provider_mode: str = "fake",
) -> ProductVideoJobHandlers:
    """Register all product-to-video pipeline job handlers with the Gate 4 dispatcher/registry."""
    if handlers_service is not None:
        service = handlers_service
        if isinstance(dispatcher, JobDispatcher):
            service.dispatcher = dispatcher
    else:
        service = ProductVideoJobHandlers(
            pi_client=pi_client,
            video_client=video_client,
            workflow_engine=workflow_engine,
            dispatcher=dispatcher if isinstance(dispatcher, JobDispatcher) else None,
            provider_mode=provider_mode,
        )

    if hasattr(dispatcher, "register"):
        for job_name, handler_func in service.get_handlers_map().items():
            dispatcher.register(job_name, handler_func)
    elif isinstance(dispatcher, dict):
        dispatcher.update(service.get_handlers_map())
    return service


def create_product_video_topic_handlers(
    workflow_engine: WorkflowEngine | None = None,
    workflow_repository: WorkflowRepository | None = None,
    handlers_service: ProductVideoJobHandlers | None = None,
    pi_client: ProductIntelligenceClient | None = None,
    video_client: VideoFactoryClient | None = None,
    tool_registry: Any | None = None,
    provider_mode: str = "configured",
    poll_timeout: float = 60.0,
    poll_interval: float = 0.5,
    creative_generator: Any | None = None,
    keyframe_runtime_factory: Callable[[], Any] | None = None,
    qc_service_factory: Callable[[Any], Any] | None = None,
    capability_snapshot: CatalogSnapshot | None = None,
) -> dict[str, Callable[[OutboxEnvelope], None]]:
    """Create production topic handlers for durable outbox delivery.

    Binds topic 'job.dispatch' to ProductVideoJobHandlers.
    """
    if (
        provider_mode == "configured"
        and capability_snapshot is None
        and workflow_repository is not None
    ):
        from hermes_personal.capabilities.discovery import CapabilityDiscovery
        from hermes_personal.capabilities.snapshots import CapabilitySnapshotRepository

        snapshot_repository = CapabilitySnapshotRepository(workflow_repository.conn)
        capability_snapshot = snapshot_repository.get_active()
        if capability_snapshot is None and tool_registry is not None and hasattr(
            tool_registry, "get_all_tool_names"
        ):
            # This is composition-root discovery, before any workflow handler
            # runs. Handlers receive only the resulting immutable snapshot and
            # never select an alias from the live registry.
            capability_snapshot = snapshot_repository.save_and_activate(
                CapabilityDiscovery().scan(tool_registry).bindings
            )
    if handlers_service is None:
        if provider_mode == "configured" and keyframe_runtime_factory is None and workflow_repository is not None:
            from hermes_personal.integrations.video_factory.keyframe_provider import (
                KeyframeOperationStore,
                KeyframeRuntime,
                VertexKeyframeProvider,
            )
            from hermes_personal.integrations.video_factory.capacity import (
                ProviderCapacityStore, configured_capacity,
            )

            from hermes_personal.product_video.storage.layout import get_workspace_layout
            workspace = get_workspace_layout().root
            keyframe_output = workspace / "keyframes"
            keyframe_runtime_factory = lambda: KeyframeRuntime(
                store=KeyframeOperationStore(workflow_repository.conn),
                provider=VertexKeyframeProvider(output_dir=keyframe_output),
                capacity_store=ProviderCapacityStore(workflow_repository.conn),
                capacity_limit=configured_capacity("vertex_keyframe"),
            )
        handlers_service = ProductVideoJobHandlers(
            pi_client=pi_client,
            video_client=video_client,
            workflow_engine=workflow_engine,
            workflow_repository=workflow_repository,
            tool_registry=tool_registry,
            provider_mode=provider_mode,
            poll_timeout=poll_timeout,
            poll_interval=poll_interval,
            creative_generator=creative_generator,
            keyframe_runtime_factory=keyframe_runtime_factory,
            capability_snapshot=capability_snapshot,
        )
    handlers_map = handlers_service.get_handlers_map()

    def _create_qc_service(connection: Any) -> Any:
        if qc_service_factory is not None:
            return qc_service_factory(connection)
        from hermes_personal.product_video.qc.service import ProductVideoQCService

        return ProductVideoQCService(connection)

    def handle_job_dispatch(envelope: OutboxEnvelope, heartbeat_fn: Callable[[], bool] | None = None) -> None:
        payload = envelope.payload
        job_name = payload.get("job_name")
        if not job_name:
            raise MalformedEnvelopeError("Missing 'job_name' in job.dispatch payload")

        if job_name not in handlers_map:
            raise ValueError(f"Unconfigured product_video job handler: {job_name!r}")

        target_wf = envelope.workflow_id
        repo = workflow_repository or (workflow_engine.repo if workflow_engine else None)
        if repo:
            with repo.conn:
                cur = repo.conn.cursor()
                cur.execute(
                    "SELECT command_id FROM processed_command WHERE workflow_id = ? AND command_id = ?",
                    (target_wf, f"cmd_{envelope.message_id}"),
                )
                if cur.fetchone():
                    return

        current_version = None
        if workflow_engine:
            res = workflow_engine.get_workflow_state(target_wf)
            if res is not None:
                current_version = res[1]
        elif workflow_repository:
            data = workflow_repository.get_workflow(target_wf)
            if data is not None:
                current_version = data[1]

        ctx = JobContext(
            workflow_id=target_wf,
            job_id=f"{job_name}.{envelope.message_id}",
            owner_user_id=payload.get("owner_user_id", "local-owner"),
            expected_version=current_version,
            idempotency_key=envelope.idempotency_key,
            heartbeat_fn=heartbeat_fn,
        )

        handler_fn = handlers_map[job_name]
        args = payload.get("args", [])
        kwargs = payload.get("kwargs", {})

        result = handler_fn(ctx, *args, **kwargs)

        if isinstance(result, JobFailed):
            if not result.retryable:
                raise TerminalJobError(f"Job execution failed [{result.code}]: {result.message}", code=result.code)
            raise JobDispatchError(f"Job execution failed [{result.code}]: {result.message}", code=result.code, retryable=True)

        if isinstance(result, JobSucceeded):
            if repo:
                wf_data = repo.get_workflow(target_wf)
                if wf_data:
                    agg, version = wf_data
                    from hermes_personal.product_video.workflow import transition
                    from hermes_personal.product_video.qc.models import QCStage

                    stage_key_map = {
                        "product_video.research": "research_result",
                        "product_video.resource_pack": "resource_pack",
                        "product_video.lock": "locked_pack",
                        "product_video.creative_brief": "creative_brief",
                        "product_video.scene_plan": "scene_plan",
                        "product_video.storyboard": "storyboard",
                        "product_video.render": "render_result",
                        "product_video.export": "export_result",
                    }
                    next_agg = dict(agg)
                    st_key = stage_key_map.get(job_name)
                    if st_key and result.artifact_ref is not None:
                        next_agg[st_key] = result.artifact_ref
                    if result.artifact_ref is not None:
                        next_agg["latest_artifact"] = result.artifact_ref

                    next_agg.pop("active_render_job_id", None)
                    next_agg.pop("active_export_job_id", None)

                    is_hitl = False
                    gate_name = None
                    outbox_next = None

                    forward_kwargs: dict[str, Any] = {}
                    if agg.get("project_id"):
                        forward_kwargs["project_id"] = agg["project_id"]
                    if agg.get("qc_authorization"):
                        forward_kwargs["qc_authorization"] = agg["qc_authorization"]
                    if agg.get("qc_max_cost_usd") is not None:
                        forward_kwargs["qc_max_cost_usd"] = agg["qc_max_cost_usd"]

                    if job_name == "product_video.research":
                        next_validated = transition(ProductVideoWorkflowState.RESEARCHING, ProductVideoWorkflowState.BUILDING_RESOURCE_PACK)
                        next_agg["state"] = next_validated.value
                        outbox_next = build_envelope(
                            workflow_id=target_wf,
                            topic="job.dispatch",
                            idempotency_key=f"idemp_pack_{target_wf}_v{version + 1}",
                            payload={
                                "job_name": "product_video.resource_pack",
                                "workflow_id": target_wf,
                                "args": [result.artifact_ref],
                                "kwargs": forward_kwargs,
                                "owner_user_id": payload.get("owner_user_id", "local-owner"),
                                "project_id": agg.get("project_id"),
                            },
                        )
                    elif job_name == "product_video.resource_pack":
                        if provider_mode == "configured":
                            repo.commit_workflow(
                                workflow_id=target_wf,
                                aggregate_json=json.dumps(next_agg),
                                events=[],
                                expected_version=version,
                            )
                            version += 1
                            qc_svc = _create_qc_service(repo.conn)
                            if heartbeat_fn is not None and not heartbeat_fn():
                                raise RuntimeError("Storyboard lease expired before keyframe QC")
                            qc_auth = agg.get("qc_authorization") or forward_kwargs.get("qc_authorization")
                            qc_max = agg.get("qc_max_cost_usd") or forward_kwargs.get("qc_max_cost_usd")
                            if qc_auth and isinstance(qc_auth, dict) and "max_cost_usd" in qc_auth and qc_max is None:
                                qc_max = qc_auth.get("max_cost_usd")
                            qc_res = qc_svc.run(
                                target_wf,
                                stage=QCStage.IMAGE,
                                provider_mode=provider_mode,
                                authorize_cost=bool(qc_auth),
                                max_cost_usd=float(qc_max) if qc_max is not None else None,
                                authorization=qc_auth,
                            )
                            if isinstance(qc_res, dict) and qc_res.get("status") == "pending":
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_authorization"
                                next_agg["operator_stage"] = QCStage.IMAGE.value
                                next_agg["operator_reason"] = qc_res.get("reason", "Configured QC requires explicit cost authorization")
                                is_hitl = False
                            elif isinstance(qc_res, dict) and qc_res.get("status") == "completed" and not _is_qc_pass(qc_res):
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_retry_authorization"
                                next_agg["operator_stage"] = QCStage.IMAGE.value
                                next_agg["operator_qc_report_id"] = qc_res.get("report_id") or (_qc_report_payload(qc_res).get("report_id"))
                                is_hitl = False
                            else:
                                next_validated = transition(ProductVideoWorkflowState.BUILDING_RESOURCE_PACK, ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK)
                                next_agg["state"] = next_validated.value
                                is_hitl = True
                                gate_name = "AwaitingProductLock"
                        else:
                            next_validated = transition(ProductVideoWorkflowState.BUILDING_RESOURCE_PACK, ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK)
                            next_agg["state"] = next_validated.value
                            is_hitl = True
                            gate_name = "AwaitingProductLock"
                    elif job_name == "product_video.retry_image_qc":
                        # Transitions back to AwaitingProductLock if retry passed, or terminal fail
                        next_validated = transition(ProductVideoWorkflowState.RETRYING_IMAGE_QC, ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK)
                        next_agg["state"] = next_validated.value
                        is_hitl = True
                        gate_name = "AwaitingProductLock"
                    elif job_name == "product_video.lock":
                        next_validated = transition(ProductVideoWorkflowState.BUILDING_RESOURCE_PACK, ProductVideoWorkflowState.CREATING_BRIEF)
                        next_agg["state"] = next_validated.value
                        rp_dict = result.artifact_ref.get("resource_pack", result.artifact_ref) if isinstance(result.artifact_ref, dict) else {}
                        product_id = str(rp_dict.get("product_id") or rp_dict.get("resource_pack_id") or rp_dict.get("id") or f"prod_{target_wf}")
                        brief_config: dict[str, Any] = {
                            "resource_pack": result.artifact_ref,
                            "project_id": agg.get("project_id"),
                        }
                        if provider_mode == "configured":
                            from hermes_personal.product_video.creative.generator import SingleModelCreativeGenerator

                            if isinstance(handlers_service.creative_generator, SingleModelCreativeGenerator):
                                brief_config["research_dossier"] = _locked_research_dossier(
                                    workflow_id=target_wf,
                                    aggregate=agg,
                                    locked_pack=result.artifact_ref,
                                    connection=repo.conn,
                                )
                        outbox_next = build_envelope(
                            workflow_id=target_wf,
                            topic="job.dispatch",
                            idempotency_key=f"idemp_brief_{target_wf}_v{version + 1}",
                            payload={
                                "job_name": "product_video.creative_brief",
                                "workflow_id": target_wf,
                                "args": [product_id, brief_config],
                                "kwargs": forward_kwargs,
                                "owner_user_id": payload.get("owner_user_id", "local-owner"),
                                "project_id": agg.get("project_id"),
                            },
                        )
                    elif job_name == "product_video.creative_brief":
                        next_validated = transition(ProductVideoWorkflowState.CREATING_BRIEF, ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL)
                        next_agg["state"] = next_validated.value
                        is_hitl = True
                        gate_name = "AwaitingBriefApproval"
                    elif job_name == "product_video.scene_plan":
                        next_validated = transition(ProductVideoWorkflowState.CREATING_SCENE_PLAN, ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL)
                        next_agg["state"] = next_validated.value
                        is_hitl = True
                        gate_name = "AwaitingSceneApproval"
                    elif job_name == "product_video.storyboard":
                        if provider_mode == "configured":
                            repo.commit_workflow(
                                workflow_id=target_wf,
                                aggregate_json=json.dumps(next_agg),
                                events=[],
                                expected_version=version,
                            )
                            version += 1
                            qc_svc = _create_qc_service(repo.conn)
                            qc_auth = agg.get("qc_authorization") or forward_kwargs.get("qc_authorization")
                            qc_max = agg.get("qc_max_cost_usd") or forward_kwargs.get("qc_max_cost_usd")
                            if qc_auth and isinstance(qc_auth, dict) and "max_cost_usd" in qc_auth and qc_max is None:
                                qc_max = qc_auth.get("max_cost_usd")
                            qc_res = qc_svc.run(
                                target_wf,
                                stage=QCStage.KEYFRAME,
                                provider_mode=provider_mode,
                                authorize_cost=bool(qc_auth),
                                max_cost_usd=float(qc_max) if qc_max is not None else None,
                                authorization=qc_auth,
                            )
                            if isinstance(qc_res, dict) and qc_res.get("status") == "pending":
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_authorization"
                                next_agg["operator_stage"] = QCStage.KEYFRAME.value
                                next_agg["operator_reason"] = qc_res.get("reason", "Configured QC requires authorization")
                                is_hitl = False
                            elif not _is_qc_pass(qc_res):
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_retry_authorization"
                                next_agg["operator_stage"] = QCStage.KEYFRAME.value
                                next_agg["operator_qc_report_id"] = qc_res.get("report_id") or (_qc_report_payload(qc_res).get("report_id"))
                                failed_report = _qc_report_payload(qc_res)
                                failed_findings = (
                                    failed_report.get("findings", {})
                                    if isinstance(failed_report, dict)
                                    else {}
                                )
                                recovery_plan = (
                                    failed_findings.get("recovery_plan")
                                    if isinstance(failed_findings, dict)
                                    else None
                                )
                                if isinstance(recovery_plan, dict):
                                    next_agg["keyframe_recovery_plan"] = recovery_plan
                                next_agg["operator_reason"] = qc_res.get(
                                    "reason",
                                    "Keyframe QC failed; apply the persisted recovery plan before regenerating and rerunning QC",
                                )
                                is_hitl = False
                            else:
                                next_validated = transition(ProductVideoWorkflowState.CREATING_STORYBOARD, ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL)
                                next_agg["state"] = next_validated.value
                                is_hitl = True
                                gate_name = "AwaitingStoryboardApproval"
                                rep = _qc_report_payload(qc_res)
                                expected_artifact = dict(result.artifact_ref)
                                expected_artifact["keyframe_qc_receipt"] = rep if rep else qc_res
                                next_agg["storyboard"] = expected_artifact
                                next_agg["latest_artifact"] = expected_artifact
                                next_agg.pop("keyframe_recovery_plan", None)
                                result = JobSucceeded(artifact_ref=expected_artifact, next_command=result.next_command)
                        else:
                            next_validated = transition(ProductVideoWorkflowState.CREATING_STORYBOARD, ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL)
                            next_agg["state"] = next_validated.value
                            is_hitl = True
                            gate_name = "AwaitingStoryboardApproval"
                    elif job_name == "product_video.render":
                        if provider_mode == "configured":
                            repo.commit_workflow(
                                workflow_id=target_wf,
                                aggregate_json=json.dumps(next_agg),
                                events=[],
                                expected_version=version,
                            )
                            version += 1
                            qc_svc = _create_qc_service(repo.conn)
                            qc_auth = agg.get("qc_authorization") or forward_kwargs.get("qc_authorization")
                            qc_max = agg.get("qc_max_cost_usd") or forward_kwargs.get("qc_max_cost_usd")
                            if qc_auth and isinstance(qc_auth, dict) and "max_cost_usd" in qc_auth and qc_max is None:
                                qc_max = qc_auth.get("max_cost_usd")
                            qc_res = qc_svc.run(
                                target_wf,
                                stage=QCStage.VIDEO,
                                provider_mode=provider_mode,
                                authorize_cost=bool(qc_auth),
                                max_cost_usd=float(qc_max) if qc_max is not None else None,
                                authorization=qc_auth,
                            )
                            if isinstance(qc_res, dict) and qc_res.get("status") == "pending":
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_authorization"
                                next_agg["operator_stage"] = QCStage.VIDEO.value
                                next_agg["operator_reason"] = qc_res.get("reason", "Configured QC requires explicit cost authorization")
                                is_hitl = False
                            elif not _is_qc_pass(qc_res):
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_retry_authorization"
                                next_agg["operator_stage"] = QCStage.VIDEO.value
                                next_agg["operator_qc_report_id"] = qc_res.get("report_id") or (_qc_report_payload(qc_res).get("report_id"))
                                next_agg["operator_reason"] = qc_res.get("reason", "Video QC did not produce a PASS verdict")
                                is_hitl = False
                            else:
                                next_validated = transition(ProductVideoWorkflowState.RENDERING, ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL)
                                next_agg["state"] = next_validated.value
                                is_hitl = True
                                gate_name = "AwaitingFinalApproval"
                        else:
                            next_validated = transition(ProductVideoWorkflowState.RENDERING, ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL)
                            next_agg["state"] = next_validated.value
                            is_hitl = True
                            gate_name = "AwaitingFinalApproval"
                    elif job_name == "product_video.export":
                        next_validated = transition(ProductVideoWorkflowState.EXPORTING, ProductVideoWorkflowState.COMPLETED)
                        next_agg["state"] = next_validated.value
                    else:
                        raise ValueError(f"Unknown job_name in handle_job_dispatch: {job_name}")

                    with repo.conn:
                        cur = repo.conn.cursor()
                        if is_hitl and gate_name:
                            approval_svc = ApprovalService(repo.conn)
                            proj_id = agg.get("project_id") or payload.get("project_id") or f"proj_{target_wf}"
                            art_dict = result.artifact_ref if isinstance(result.artifact_ref, dict) else {}
                            art_id = (
                                art_dict.get("artifact_id")
                                or art_dict.get("brief_id")
                                or art_dict.get("scene_plan_id")
                                or art_dict.get("storyboard_id")
                                or art_dict.get("render_id")
                                or art_dict.get("export_id")
                                or art_dict.get("resource_pack_id")
                                or art_dict.get("id")
                            )
                            art_ver = art_dict.get("version") or art_dict.get("resource_pack_version")
                            approval_payload = {
                                "workflow_id": target_wf,
                                "project_id": proj_id,
                                "gate": gate_name,
                                "workflow_version": version + 1,
                                "artifact_ref": result.artifact_ref,
                                "owner_user_id": payload.get("owner_user_id", "local-owner"),
                            }
                            if art_id is not None:
                                approval_payload["artifact_id"] = art_id
                            if art_ver is not None:
                                approval_payload["artifact_version"] = art_ver
                            req_id = approval_svc.submit_request(
                                approval_payload,
                                cursor=cur,
                            )
                            next_agg["pending_approval_gate"] = gate_name
                            next_agg["pending_approval_id"] = req_id
                        else:
                            next_agg.pop("pending_approval_gate", None)
                            next_agg.pop("pending_approval_id", None)

                        repo.commit_workflow(
                            workflow_id=target_wf,
                            aggregate_json=json.dumps(next_agg),
                            events=[
                                {
                                    "event_id": f"evt_{envelope.message_id}",
                                    "command_id": f"cmd_{envelope.message_id}",
                                    "event_type": "JobSucceeded",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "payload": {"job_name": job_name, "artifact_ref": result.artifact_ref},
                                }
                            ],
                            outbox_message=outbox_next,
                            expected_version=version,
                        )

    return {"job.dispatch": handle_job_dispatch}


def start_product_video_workflow(
    workflow_repository: WorkflowRepository,
    workflow_id: str,
    product_name: str,
    keywords: list[str],
    pdp_url: str | None = None,
    owner_user_id: str = "local-owner",
    idempotency_key: str | None = None,
    project_id: str | None = None,
    source_context: dict[str, Any] | None = None,
    qc_authorization: dict[str, Any] | None = None,
    qc_max_cost_usd: float | None = None,
    research_snapshot_id: str | None = None,
) -> str:
    """Production entrypoint to create and enqueue a durable Product-to-Video workflow.

    Commits aggregate state 'researching', appends 'WorkflowStarted' event,
    and enqueues the 'job.dispatch' OutboxEnvelope for product_video.research.
    """
    if not project_id or not str(project_id).strip():
        raise ValueError("project_id is required")
    effective_project_id = str(project_id).strip()
    idemp = idempotency_key or f"idemp_res_{workflow_id}"
    effective_kwargs: dict[str, Any] = {"project_id": effective_project_id}
    if source_context:
        for k in ("canonical_product_key", "brand", "model", "variant", "images", "source_product_id"):
            if k in source_context and source_context[k] is not None:
                effective_kwargs[k] = source_context[k]
    effective_kwargs.update(_qc_context({
        "qc_authorization": qc_authorization,
        "qc_max_cost_usd": qc_max_cost_usd,
    }, workflow_id=workflow_id))
    if research_snapshot_id:
        effective_kwargs["research_snapshot_id"] = str(research_snapshot_id)

    outbox_msg = build_envelope(
        workflow_id=workflow_id,
        topic="job.dispatch",
        idempotency_key=idemp,
        payload={
            "job_name": "product_video.research",
            "workflow_id": workflow_id,
            "project_id": effective_project_id,
            "args": [product_name, keywords, pdp_url],
            "owner_user_id": owner_user_id,
            "kwargs": effective_kwargs,
        },
    )
    aggregate: dict[str, Any] = {
        "state": ProductVideoWorkflowState.RESEARCHING.value,
        "project_id": effective_project_id,
        "owner_user_id": owner_user_id,
        "pdp_url": pdp_url,
    }
    if source_context is not None:
        aggregate["source_context"] = source_context
        aggregate["product_key"] = source_context.get("product_key")
    aggregate.update(_qc_context({
        "qc_authorization": qc_authorization,
        "qc_max_cost_usd": qc_max_cost_usd,
    }, workflow_id=workflow_id))
    if research_snapshot_id:
        aggregate["research_snapshot_id"] = str(research_snapshot_id)

    workflow_repository.commit_workflow(
        workflow_id=workflow_id,
        aggregate_json=json.dumps(aggregate),
        events=[
            {
                "event_id": f"evt_start_{workflow_id}",
                "command_id": f"cmd_start_{workflow_id}",
                "event_type": "WorkflowStarted",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"product_name": product_name, "keywords": keywords, "pdp_url": pdp_url, "project_id": effective_project_id},
            }
        ],
        outbox_message=outbox_msg,
        expected_version=0,
    )
    return workflow_id
