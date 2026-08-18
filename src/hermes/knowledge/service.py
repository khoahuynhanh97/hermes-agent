from typing import List, Optional
from sqlmodel import Session, select

from .db import get_session
from .models import BrandGuideline, ViralVideoPlaybook, PromptTemplate, LessonLearned, BrandSafetyRule


class KnowledgeService:
    def __init__(self, session: Session):
        self.session = session

    # --- BrandGuideline ---
    def get_brand_guideline(self, project_id: str) -> Optional[BrandGuideline]:
        statement = select(BrandGuideline).where(BrandGuideline.project_id == project_id)
        return self.session.exec(statement).first()

    def save_brand_guideline(self, guideline: BrandGuideline) -> BrandGuideline:
        # In a real app, you might upsert instead of just adding.
        self.session.add(guideline)
        self.session.commit()
        self.session.refresh(guideline)
        return guideline

    # --- ViralVideoPlaybook ---
    def list_playbooks(self, category: Optional[str] = None) -> List[ViralVideoPlaybook]:
        statement = select(ViralVideoPlaybook)
        if category:
            statement = statement.where(ViralVideoPlaybook.category == category)
        return self.session.exec(statement).all()

    def save_playbook(self, playbook: ViralVideoPlaybook) -> ViralVideoPlaybook:
        self.session.add(playbook)
        self.session.commit()
        self.session.refresh(playbook)
        return playbook

    # --- PromptTemplate ---
    def list_prompt_templates(self, industry: Optional[str] = None, category: Optional[str] = None) -> List[PromptTemplate]:
        statement = select(PromptTemplate)
        if industry:
            statement = statement.where(PromptTemplate.industry == industry)
        if category:
            statement = statement.where(PromptTemplate.category == category)
        return self.session.exec(statement).all()
        
    def save_prompt_template(self, template: PromptTemplate) -> PromptTemplate:
        self.session.add(template)
        self.session.commit()
        self.session.refresh(template)
        return template

    # --- LessonLearned ---
    def get_lessons_for_project(self, project_id: str) -> List[LessonLearned]:
        statement = select(LessonLearned).where(LessonLearned.project_id == project_id)
        return self.session.exec(statement).all()

    def save_lesson(self, lesson: LessonLearned) -> LessonLearned:
        self.session.add(lesson)
        self.session.commit()
        self.session.refresh(lesson)
        return lesson

    # --- BrandSafetyRule ---
    def list_brand_safety_rules(self, project_id: str) -> List[BrandSafetyRule]:
        statement = select(BrandSafetyRule).where(
            BrandSafetyRule.project_id == project_id,
            BrandSafetyRule.enabled == True,
        )
        return self.session.exec(statement).all()

    def save_brand_safety_rule(self, rule: BrandSafetyRule) -> BrandSafetyRule:
        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return rule

    def delete_brand_safety_rule(self, rule_id: int) -> bool:
        rule = self.session.get(BrandSafetyRule, rule_id)
        if rule is None:
            return False
        self.session.delete(rule)
        self.session.commit()
        return True


# Dependency for FastAPI or other frameworks
def get_knowledge_service() -> KnowledgeService:
    with get_session() as session:
        yield KnowledgeService(session)
