from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from hermes_personal.product_video.handlers import _locked_research_dossier
from hermes_personal.product_video.qc.models import QCReport, QCStage, QCVerdict
from hermes_personal.product_video.qc.repository import QCReportRepository


def _grounding_inputs(tmp_path: Path) -> tuple[sqlite3.Connection, dict, dict]:
    connection = sqlite3.connect(":memory:")
    manifest = []
    for index in (1, 2):
        path = tmp_path / f"product-{index}.png"
        path.write_bytes(f"product-{index}".encode())
        manifest.append({
            "asset_id": f"asset-{index}", "uri": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "eligible": True,
        })
    QCReportRepository(connection).save_report(QCReport(
        report_id="image-pass", workflow_id="pv-grounding", stage=QCStage.IMAGE,
        artifact_id="pack-1", artifact_version=1, artifact_digest="pack-digest",
        reference_digests=[item["sha256"] for item in manifest],
        evaluator_name="offline", evaluator_version="1", rubric_version="2",
        created_at=datetime.now(timezone.utc).isoformat(), score=90,
        verdict=QCVerdict.PASS, findings={"eligible_reference_manifest": manifest},
    ))
    pack = {
        "resource_pack_id": "pack-1", "snapshot_id": "snapshot-1",
        "canonical_product_id": "product-baseus", "variant_id": "black",
        "product_identity": {"brand": "Baseus", "model": "Bowie WM02", "variant": "black"},
        "claims": [
            {"claim_id": "claim-a", "text": "Charging case included", "status": "verified", "evidence_refs": ["ev-a"]},
            {"claim_id": "claim-b", "text": "Bluetooth supported", "status": "supported", "evidence_refs": ["ev-b"]},
            {"claim_id": "claim-c", "text": "Waterproof", "status": "unverified", "evidence_refs": ["ev-c"]},
            {"claim_id": "claim-cross", "text": "Other product", "status": "verified", "evidence_refs": ["ev-other"]},
            {"claim_id": "claim-unknown", "text": "Unknown", "status": "verified", "evidence_refs": ["missing"]},
            {"text": "No canonical claim identity", "status": "verified", "evidence_refs": ["ev-a"]},
        ],
    }
    evidence = [
        {"evidence_id": evidence_id, "snapshot_id": "snapshot-1", "canonical_product_id": product_id, "variant_id": "black"}
        for evidence_id, product_id in (
            ("ev-a", "product-baseus"), ("ev-b", "product-baseus"),
            ("ev-c", "product-baseus"), ("ev-other", "other-product"),
        )
    ]
    aggregate = {
        "resource_pack": pack,
        "research_result": {"raw_result": {
            "evidence": evidence,
            "source_results": [{"url": "https://www.baseus.com/p/wm02", "usable": True}],
            "discovered_sources": [{
                "url": "https://www.baseus.com/p/wm02", "source_class": "official",
            }],
        }},
    }
    return connection, aggregate, {"raw_result": pack}


def test_locked_dossier_preserves_claim_specific_evidence_and_official_source(tmp_path: Path) -> None:
    connection, aggregate, lock = _grounding_inputs(tmp_path)
    first = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate, locked_pack=lock, connection=connection,
    )
    second = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate, locked_pack=lock, connection=connection,
    )
    assert first["verified_claims"] == (
        {"claim_id": "claim-a", "text": "Charging case included", "evidence_refs": ("ev-a",)},
        {"claim_id": "claim-b", "text": "Bluetooth supported", "evidence_refs": ("ev-b",)},
    )
    assert first["source_refs"] == ("https://www.baseus.com/p/wm02",)
    assert first["dossier_digest"] == second["dossier_digest"]


def test_locked_dossier_excludes_pack_claim_without_resolvable_evidence(tmp_path: Path) -> None:
    connection, aggregate, lock = _grounding_inputs(tmp_path)
    aggregate["research_result"]["raw_result"].pop("evidence")
    dossier = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate, locked_pack=lock, connection=connection,
    )
    assert dossier["verified_claims"] == ()


def test_locked_dossier_accepts_only_official_source_claim_with_direct_evidence(tmp_path: Path) -> None:
    connection, aggregate, lock = _grounding_inputs(tmp_path)
    pack = aggregate["resource_pack"]
    pack["claims"] = [{
        "claim_id": "claim-real", "text": "Ra90 high CRI", "status": "source_claim",
        "evidence_refs": ["ev-real"], "snapshot_id": "snapshot-1",
        "canonical_product_id": "product-baseus", "variant_id": "black",
    }]
    pack["evidence"] = [{
        "evidence_id": "ev-real", "snapshot_id": "snapshot-1",
        "canonical_product_id": "product-baseus", "variant_id": "black",
        "source": {"canonical_url": "https://www.baseus.com/p/wm02"},
    }]
    dossier = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate, locked_pack={"raw_result": pack}, connection=connection,
    )
    assert dossier["verified_claims"] == ({
        "claim_id": "claim-real", "text": "Ra90 high CRI", "evidence_refs": ("ev-real",),
    },)
    pack["evidence"][0]["source"]["canonical_url"] = "https://seller.example/wm02"
    rejected = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate, locked_pack={"raw_result": pack}, connection=connection,
    )
    assert rejected["verified_claims"] == ()


def test_locked_dossier_reads_direct_evidence_from_persisted_pack_raw_result(tmp_path: Path) -> None:
    connection, aggregate, _ = _grounding_inputs(tmp_path)
    pack = aggregate["resource_pack"]
    pack["claims"] = [{
        "claim_id": "claim-official", "text": "Ra90 high CRI", "status": "source_claim",
        "evidence_refs": ["ev-official"], "snapshot_id": "snapshot-1",
        "canonical_product_id": "product-baseus", "variant_id": "black",
    }]
    pack["raw_result"] = {
        "evidence": [{
            "evidence_id": "ev-official", "snapshot_id": "snapshot-1",
            "canonical_product_id": "product-baseus", "variant_id": "black",
            "source": {"canonical_url": "https://www.baseus.com/p/wm02"},
        }],
        "source_results": [{"url": "https://www.baseus.com/p/wm02", "usable": True}],
        "discovered_sources": [{
            "url": "https://www.baseus.com/p/wm02", "source_class": "official",
        }],
    }
    aggregate["research_result"]["raw_result"].pop("evidence")

    dossier = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate,
        locked_pack={"raw_result": {"resolved_values": {}}}, connection=connection,
    )

    assert dossier["verified_claims"] == ({
        "claim_id": "claim-official", "text": "Ra90 high CRI",
        "evidence_refs": ("ev-official",),
    },)


def test_locked_dossier_does_not_promote_scouting_copy_to_use_case(tmp_path: Path) -> None:
    connection, aggregate, lock = _grounding_inputs(tmp_path)
    aggregate["source_context"] = {
        "hot_reason": "Protects eyes from all harmful blue light",
    }

    dossier = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate,
        locked_pack=lock, connection=connection,
    )

    assert dossier["use_cases"] == ()
    assert "Protects eyes" not in str(dossier)


def test_locked_dossier_accepts_classified_explicit_official_source(tmp_path: Path) -> None:
    connection, aggregate, lock = _grounding_inputs(tmp_path)
    raw = aggregate["research_result"]["raw_result"]
    raw["discovered_sources"] = []
    raw["source_results"][0]["source_class"] = "official"
    pack = aggregate["resource_pack"]
    pack["claims"] = [{
        "claim_id": "claim-real", "text": "Ra90 high CRI", "status": "source_claim",
        "evidence_refs": ["ev-a"], "snapshot_id": "snapshot-1",
        "canonical_product_id": "product-baseus", "variant_id": "black",
    }]
    raw["evidence"][0]["source"] = {"canonical_url": "https://www.baseus.com/p/wm02"}
    dossier = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate, locked_pack=lock, connection=connection,
    )
    assert dossier["source_refs"] == ("https://www.baseus.com/p/wm02",)
    assert len(dossier["verified_claims"]) == 1


def test_locked_dossier_recognizes_exact_brand_site_and_deduplicates_claims(tmp_path: Path) -> None:
    connection, aggregate, lock = _grounding_inputs(tmp_path)
    raw = aggregate["research_result"]["raw_result"]
    raw["discovered_sources"] = []
    raw["source_results"] = [{
        "url": "https://baseus.com/p/wm02", "source_class": "unknown", "usable": True,
    }]
    pack = aggregate["resource_pack"]
    pack["claims"] = [
        {
            "claim_id": f"claim-{index}", "text": "Charging case included",
            "status": "source_claim", "evidence_refs": ["ev-a"],
        }
        for index in (1, 2)
    ]
    raw["evidence"][0]["source"] = {
        "canonical_url": "https://baseus.com/p/WM02",
        "final_url": "https://baseus.com/p/wm02",
    }
    dossier = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate, locked_pack=lock, connection=connection,
    )
    assert dossier["source_refs"] == ("https://baseus.com/p/wm02",)
    assert dossier["verified_claims"] == ({
        "claim_id": "claim-1", "text": "Charging case included", "evidence_refs": ("ev-a",),
    },)

    raw["source_results"][0]["url"] = "https://baseus.com.evil.example/p/wm02"
    raw["evidence"][0]["source"]["final_url"] = "https://baseus.com.evil.example/p/wm02"
    rejected = _locked_research_dossier(
        workflow_id="pv-grounding", aggregate=aggregate, locked_pack=lock, connection=connection,
    )
    assert rejected["verified_claims"] == ()
