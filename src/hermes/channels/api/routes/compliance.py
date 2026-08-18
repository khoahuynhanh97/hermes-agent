"""Compliance API routes — brand safety, asset rights, AIGC watermark checks."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from hermes.knowledge.db import get_session
from hermes.knowledge.service import KnowledgeService
from hermes.knowledge.models import BrandSafetyRule
from hermes.compliance.brand_safety import BrandSafetyFilter
from hermes.compliance.gateway import ComplianceGateway

router = APIRouter()


def _get_service():
    with get_session() as session:
        yield KnowledgeService(session)


# ── Brand Safety Check ─────────────────────────────────────────────────

class BrandSafetyCheckRequest(BaseModel):
    text: str
    project_id: Optional[str] = None


@router.post("/check")
def run_compliance_check(body: BrandSafetyCheckRequest):
    """Run brand safety check on text content."""
    filter_obj = BrandSafetyFilter()
    return filter_obj.scan_text(body.text)


@router.post("/brand-safety", status_code=201)
def add_brand_safety_rule(
    body: dict,
    svc: KnowledgeService = Depends(_get_service),
):
    """Add a custom brand safety rule for a project."""
    rule = BrandSafetyRule(
        project_id=body["project_id"],
        rule_name=body["rule_name"],
        pattern=body["pattern"],
        severity=body.get("severity", "high"),
        replacement_hint=body.get("replacement_hint", ""),
        enabled=body.get("enabled", True),
    )
    saved = svc.save_brand_safety_rule(rule)
    return saved.model_dump()


@router.get("/brand-safety/{project_id}")
def get_brand_safety_rules(
    project_id: str,
    svc: KnowledgeService = Depends(_get_service),
):
    """Get all brand safety rules for a project."""
    rules = svc.list_brand_safety_rules(project_id)
    return [r.model_dump() for r in rules]


@router.delete("/brand-safety/{rule_id}")
def delete_brand_safety_rule(
    rule_id: int,
    svc: KnowledgeService = Depends(_get_service),
):
    """Delete a brand safety rule."""
    deleted = svc.delete_brand_safety_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "deleted", "rule_id": rule_id}


# ── Compliance Report ──────────────────────────────────────────────────

class FullCheckRequest(BaseModel):
    project_id: str
    video_path: str = ""
    voiceover_text: str = ""
    caption_text: str = ""
    resource_pack: dict = {}


@router.post("/report/{project_id}")
def get_compliance_report(
    project_id: str,
    body: FullCheckRequest,
):
    """Run full compliance check and produce a report."""
    gateway = ComplianceGateway()
    result = gateway.run_full_check(
        project_id=project_id,
        video_path=body.video_path,
        voiceover_text=body.voiceover_text,
        caption_text=body.caption_text,
        resource_pack=body.resource_pack,
    )
    return result
