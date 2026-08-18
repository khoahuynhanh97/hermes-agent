from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from sqlmodel import select
from hermes.knowledge.db import get_session
from hermes.knowledge.service import KnowledgeService
from hermes.knowledge.models import (
    BrandGuideline,
    ViralVideoPlaybook,
    PromptTemplate,
    LessonLearned,
)

router = APIRouter()


def _get_service():
    with get_session() as session:
        yield KnowledgeService(session)


# ── Playbooks ────────────────────────────────────────────────────────────

class PlaybookCreateRequest(BaseModel):
    name: str
    structure: str
    description: str
    category: str


@router.get("/playbooks")
def list_playbooks(
    category: Optional[str] = Query(None),
    svc: KnowledgeService = Depends(_get_service),
):
    return [p.model_dump() for p in svc.list_playbooks(category=category)]


@router.get("/playbooks/{playbook_id}")
def get_playbook(
    playbook_id: int,
    svc: KnowledgeService = Depends(_get_service),
):
    all_playbooks = svc.list_playbooks()
    for p in all_playbooks:
        if p.id == playbook_id:
            return p.model_dump()
    raise HTTPException(status_code=404, detail="Playbook not found")


@router.post("/playbooks", status_code=201)
def create_playbook(
    body: PlaybookCreateRequest,
    svc: KnowledgeService = Depends(_get_service),
):
    saved = svc.save_playbook(ViralVideoPlaybook.model_validate(body.model_dump()))
    return saved.model_dump()


# ── Prompt Templates ─────────────────────────────────────────────────────

class TemplateCreateRequest(BaseModel):
    name: str
    template: str
    category: str
    industry: str


@router.get("/templates")
def list_templates(
    industry: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    svc: KnowledgeService = Depends(_get_service),
):
    return [t.model_dump() for t in svc.list_prompt_templates(industry=industry, category=category)]


@router.get("/templates/{template_id}")
def get_template(
    template_id: int,
    svc: KnowledgeService = Depends(_get_service),
):
    all_templates = svc.list_prompt_templates()
    for t in all_templates:
        if t.id == template_id:
            return t.model_dump()
    raise HTTPException(status_code=404, detail="Template not found")


@router.post("/templates", status_code=201)
def create_template(
    body: TemplateCreateRequest,
    svc: KnowledgeService = Depends(_get_service),
):
    saved = svc.save_prompt_template(PromptTemplate.model_validate(body.model_dump()))
    return saved.model_dump()


# ── Brand Guidelines ─────────────────────────────────────────────────────

class BrandCreateRequest(BaseModel):
    project_id: str
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    tone_of_voice: Optional[str] = None


@router.get("/brands/{project_id}")
def get_brand(
    project_id: str,
    svc: KnowledgeService = Depends(_get_service),
):
    brand = svc.get_brand_guideline(project_id)
    if brand is None:
        return {"project_id": project_id, "primary_color": None, "secondary_color": None, "accent_color": None, "tone_of_voice": None}
    return brand.model_dump()


@router.post("/brands", status_code=201)
def save_brand(
    body: BrandCreateRequest,
    svc: KnowledgeService = Depends(_get_service),
):
    saved = svc.save_brand_guideline(BrandGuideline.model_validate(body.model_dump()))
    return saved.model_dump()


# ── Lessons ──────────────────────────────────────────────────────────────

class LessonCreateRequest(BaseModel):
    video_id: str
    project_id: str
    feedback: str
    lesson: str
    tags: Optional[str] = None


@router.get("/lessons")
def list_lessons(
    project_id: Optional[str] = Query(None),
    svc: KnowledgeService = Depends(_get_service),
):
    if project_id:
        return [l.model_dump() for l in svc.get_lessons_for_project(project_id)]
    return [l.model_dump() for l in svc.session.exec(select(LessonLearned)).all()]


@router.get("/lessons/{project_id}")
def get_lessons(
    project_id: str,
    svc: KnowledgeService = Depends(_get_service),
):
    return [l.model_dump() for l in svc.get_lessons_for_project(project_id)]


@router.post("/lessons", status_code=201)
def create_lesson(
    body: LessonCreateRequest,
    svc: KnowledgeService = Depends(_get_service),
):
    saved = svc.save_lesson(LessonLearned.model_validate(body.model_dump()))
    return saved.model_dump()


# ── Search ───────────────────────────────────────────────────────────────

@router.get("/search")
def search_knowledge(
    q: Optional[str] = Query(None),
    type: Optional[str] = Query(None, alias="type"),
    category: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    svc: KnowledgeService = Depends(_get_service),
):
    results: list[dict] = []

    def _match(item: dict) -> bool:
        if q:
            text = f"{item.get('name', '')} {item.get('description', '')} {item.get('template', '')} {item.get('lesson', '')} {item.get('feedback', '')}".lower()
            if q.lower() not in text:
                return False
        if category and item.get("category", "") != category:
            return False
        if industry and item.get("industry", "") != industry:
            return False
        return True

    if type is None or type == "playbook":
        results += [p.model_dump() for p in svc.list_playbooks(category=category) if _match(p.model_dump())]
    if type is None or type == "template":
        results += [t.model_dump() for t in svc.list_prompt_templates(industry=industry, category=category) if _match(t.model_dump())]
    if type is None or type == "lesson":
        all_lessons = svc.session.exec(select(LessonLearned)).all()
        results += [l.model_dump() for l in all_lessons if _match(l.model_dump())]
    if type is None or type == "brand":
        all_brands = svc.session.exec(select(BrandGuideline)).all()
        results += [b.model_dump() for b in all_brands if _match(b.model_dump())]

    return results
