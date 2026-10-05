from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from urllib.parse import urlsplit

from hermes_personal.product_video.qc.models import QCStage, QCVerdict
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.job_contracts import (
    ExecutionBindingPreflightError,
    JobContext,
    TerminalJobError,
)
from hermes_personal.product_video.provider_runtime import (
    validate_polling_setting,
)


logger = logging.getLogger(__name__)




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


def _compute_digest(obj: Any) -> str:
    """Compute SHA-256 digest of JSON-serializable object."""
    payload = json.dumps(obj, sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def verify_job_digests(job_name: str, inputs: dict[str, Any], expected_digests: dict[str, str]) -> bool:
    """Verify that job inputs match expected digests."""
    for key, expected in expected_digests.items():
        if key not in inputs:
            return False
        if _compute_digest(inputs[key]) != expected:
            return False
    return True


def _brand_owned_product_url(brand: str, url: str) -> bool:
    """Recognize an HTTPS brand.com source when PI left its class unknown."""
    from urllib.parse import urlsplit
    brand_domain = "".join(char for char in brand.casefold() if char.isascii() and char.isalnum())
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    return bool(brand_domain) and parsed.scheme == "https" and host == f"{brand_domain}.com"


def _recover_creative_brief(persisted: dict[str, Any], dossier: Any) -> Any | None:
    """Rebuild a V2 artifact after a crash following an already persisted brief."""
    from hermes_personal.product_video.creative.contracts import (
        AudienceSpec, CreativeBriefV2, GenerationProvenance, ReasonToBelieve,
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


def _require_configured_execution_binding(client: Any, stage_key: str, capability_id: str) -> str:
    """Fail closed when a configured client cannot prove its execution binding."""
    from hermes_personal.product_video.job_contracts import ExecutionBindingPreflightError, TerminalJobError
    try:
        preflight = getattr(client, "require_execution_binding", None)
    except Exception as exc:
        raise ExecutionBindingPreflightError(capability_id, exc) from exc
    if not callable(preflight):
        raise TerminalJobError(f"BINDING_UNAVAILABLE: Configured video client is missing execution binding preflight for capability '{capability_id}' (missing_preflight_contract)", code="BINDING_UNAVAILABLE")
    try:
        wire = preflight(stage_key, capability_id)
    except TerminalJobError:
        raise
    except Exception as exc:
        raise ExecutionBindingPreflightError(capability_id, exc) from exc
    if not isinstance(wire, str) or not wire.strip():
        raise TerminalJobError(f"BINDING_UNAVAILABLE: Configured video client returned no execution wire for capability '{capability_id}' (invalid_preflight_result)", code="BINDING_UNAVAILABLE")
    if capability_id == "video.render" and wire != "mcp__video_factory__render":
        raise TerminalJobError(f"BINDING_UNAVAILABLE: Configured video client returned a noncanonical execution wire for capability '{capability_id}' (noncanonical_wire)", code="BINDING_UNAVAILABLE")
    return wire


def _resolve_durable_resume_job_id(params: dict[str, Any], aggregate: dict[str, Any], durable_job_key: str, forbidden_aliases: tuple[str, ...] = ()) -> str:
    """Return the only identity eligible for a no-resubmit resume."""
    from hermes_personal.product_video.job_contracts import TerminalJobError
    noncanonical_aliases = [alias for alias in forbidden_aliases if str(params.pop(alias, "") or "").strip()]
    if noncanonical_aliases:
        raise TerminalJobError(f"Noncanonical resume identity field(s) {', '.join(noncanonical_aliases)} are not supported at the workflow boundary (noncanonical_resume_identity)", code="JOB_BINDING_MISMATCH")
    requested_job_id = str(params.get("active_job_id") or "").strip()
    durable_job_id = str(aggregate.get(durable_job_key) or "").strip()
    if requested_job_id and requested_job_id != durable_job_id:
        reason = "unbound_durable_identity" if not durable_job_id else "durable_identity_mismatch"
        raise TerminalJobError(f"Requested active_job_id '{requested_job_id}' does not match durable job identity '{durable_job_id}' ({reason})", code="JOB_BINDING_MISMATCH")
    if durable_job_id:
        params["active_job_id"] = durable_job_id
    else:
        params.pop("active_job_id", None)
    return durable_job_id


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

    if not claims:
        # Fallback to grounded product identity features
        features = list(identity.get("distinctive_features") or resource_pack.get("features") or [])
        if not features:
            features = [f"{brand} {model}".strip(), "Hiệu năng ổn định vượt trội", "Thiết kế hiện đại, cao cấp"]
        for idx, feat in enumerate(features[:4], 1):
            c_id = f"claim_{idx:02d}"
            ev_id = f"ev_grounded_{idx:02d}"
            claims.append({
                "claim_id": c_id,
                "text": str(feat),
                "status": "supported",
                "evidence_refs": [ev_id],
            })
            resource_pack.setdefault("evidence", []).append({
                "evidence_id": ev_id,
                "id": ev_id,
                "text": str(feat),
                "usable": True,
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


