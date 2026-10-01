"""Build grounded creative dossiers from locked PI and fresh Image QC artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping, Sequence

from hermes_personal.product_video.qc.models import QCReport, QCStage, QCVerdict

from .contracts import EligibleAsset, EvidenceClaim, ProductIdentityV2, ResearchDossier


class DossierBuildError(ValueError):
    pass


def _path(value: object) -> Path:
    raw = str(value or "").strip()
    if raw.startswith("file://"):
        raw = raw[7:]
        while raw.startswith(("/", "\\")) and not (
            len(raw) >= 2 and raw[0].isalpha() and raw[1] == ":"
        ):
            raw = raw[1:]
    return Path(raw).resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _identity(resource_pack: Mapping[str, object]) -> ProductIdentityV2:
    identity = resource_pack.get("product_identity")
    if not isinstance(identity, Mapping):
        identity = {}
    resolved = resource_pack.get("resolved_values")
    if not isinstance(resolved, Mapping):
        resolved = {}
    brand = str(identity.get("brand") or resolved.get("brand") or resource_pack.get("brand") or "").strip()
    model = str(identity.get("model") or resolved.get("model") or resource_pack.get("model") or "").strip()
    variant = str(identity.get("variant") or resolved.get("variant") or resource_pack.get("variant") or "").strip()
    display_name = str(
        identity.get("display_name")
        or identity.get("name")
        or resolved.get("name")
        or resource_pack.get("product_name")
        or f"{brand} {model}".strip()
    ).strip()
    distinctive = _strings(identity.get("distinctive_features"))
    try:
        return ProductIdentityV2(
            brand=brand,
            model=model,
            variant=variant,
            display_name=display_name,
            distinctive_features=distinctive,
            shape=str(identity.get("shape") or "").strip(),
            color=str(identity.get("color") or "").strip(),
            materials=str(identity.get("materials") or identity.get("material") or "").strip(),
            logo_placement=str(identity.get("logo_placement") or "").strip(),
            silhouette=str(identity.get("silhouette") or "").strip(),
            main_proportions=str(identity.get("main_proportions") or "").strip(),
            product_count=str(identity.get("product_count") or "").strip(),
            control_placement=str(identity.get("control_placement") or "").strip(),
            port_count=str(identity.get("port_count") or "").strip(),
            port_placement=str(identity.get("port_placement") or "").strip(),
            display_shape=str(identity.get("display_shape") or "").strip(),
        )
    except ValueError as exc:
        raise DossierBuildError(f"invalid locked product identity: {exc}") from exc


def _claims(snapshot: Mapping[str, object]) -> tuple[EvidenceClaim, ...]:
    raw_claims = snapshot.get("claims") or snapshot.get("verified_claims") or []
    if not isinstance(raw_claims, (list, tuple)):
        return ()
    claims: list[EvidenceClaim] = []
    for index, item in enumerate(raw_claims, start=1):
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status not in {"verified", "supported", "confirmed"}:
            continue
        refs = _strings(item.get("evidence_refs") or item.get("sources"))
        text = str(item.get("text") or item.get("claim") or "").strip()
        if not text or not refs:
            continue
        claims.append(
            EvidenceClaim(
                claim_id=str(item.get("claim_id") or item.get("id") or f"claim-{index:02d}"),
                text=text,
                evidence_refs=refs,
            )
        )
    return tuple(claims)


def _eligible_assets(report: QCReport) -> tuple[EligibleAsset, ...]:
    raw_manifest = report.findings.get("eligible_reference_manifest", [])
    if not isinstance(raw_manifest, list):
        raise DossierBuildError("Image QC eligible reference manifest is missing")
    assets: list[EligibleAsset] = []
    for item in raw_manifest:
        if not isinstance(item, Mapping) or item.get("eligible") is not True:
            continue
        asset_id = str(item.get("asset_id") or "").strip()
        asset_path = _path(item.get("uri") or item.get("path") or item.get("local_path"))
        expected = str(item.get("sha256") or item.get("digest") or "").removeprefix("sha256:")
        if not asset_path.is_file() or asset_path.stat().st_size == 0:
            raise DossierBuildError(f"eligible asset is missing or empty: {asset_id}")
        actual = _sha256(asset_path)
        if actual != expected:
            raise DossierBuildError(f"eligible asset digest mismatch: {asset_id}")
        assets.append(
            EligibleAsset(
                asset_id=asset_id,
                path=str(asset_path),
                sha256=actual,
                qc_report_id=report.report_id,
                visual_observations=_strings(item.get("visual_observations")),
                reference_rank=int(item.get("reference_rank", 0) or 0),
                qc_score=int(item.get("qc_score", item.get("score", 0)) or 0),
                identity_score=int(item.get("identity_score", 0) or 0),
                clarity_score=int(item.get("clarity_score", 0) or 0),
                usability_score=int(item.get("usability_score", 0) or 0),
                view_angle=str(item.get("view_angle") or ""),
                shot_type=str(item.get("shot_type") or ""),
                visible_details=_strings(item.get("visible_details")),
                scene_suitability=_strings(item.get("scene_suitability")),
                risk_flags=_strings(item.get("risk_flags")),
            )
        )
    return tuple(assets)


def build_research_dossier(
    *,
    workflow_id: str,
    resource_pack: Mapping[str, object],
    qc_report: QCReport,
    research_snapshot: Mapping[str, object],
    approved_learnings: Sequence[Mapping[str, object]] = (),
) -> ResearchDossier:
    if qc_report.workflow_id != workflow_id:
        raise DossierBuildError("Image QC workflow does not match dossier workflow")
    if qc_report.stage != QCStage.IMAGE or qc_report.verdict != QCVerdict.PASS:
        raise DossierBuildError("a passing Image QC report is required")
    try:
        return ResearchDossier.create(
            workflow_id=workflow_id,
            product_identity=_identity(resource_pack),
            verified_claims=_claims(research_snapshot),
            eligible_assets=_eligible_assets(qc_report),
            restricted_claims=_strings(research_snapshot.get("restricted_claims") or research_snapshot.get("restrictions")),
            audience_signals=_strings(research_snapshot.get("audience_signals")),
            pain_points=_strings(research_snapshot.get("pain_points")),
            use_cases=_strings(research_snapshot.get("use_cases")),
            differentiators=_strings(research_snapshot.get("differentiators")),
            approved_learnings=tuple(dict(item) for item in approved_learnings),
            source_refs=_strings(research_snapshot.get("source_refs")),
        )
    except ValueError as exc:
        raise DossierBuildError(str(exc)) from exc
