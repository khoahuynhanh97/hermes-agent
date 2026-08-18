from typing import Optional
from sqlmodel import Field, SQLModel


class BrandGuideline(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(index=True)
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    tone_of_voice: Optional[str] = None


class ViralVideoPlaybook(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    structure: str  # e.g., "Hook (3s) -> Problem (5s) -> Agitate (5s) -> Solution (10s) -> CTA (3s)"
    description: str
    category: str


class PromptTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    template: str
    category: str  # e.g., "Technology", "Cosmetics", "Fashion"
    industry: str


class LessonLearned(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str
    project_id: str
    feedback: str
    lesson: str
    tags: Optional[str] = None # Comma-separated


class BrandSafetyRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(index=True)
    rule_name: str  # e.g., "No absolute claims"
    pattern: str  # regex pattern
    severity: str = "high"  # high, medium, low
    replacement_hint: str = ""
    enabled: bool = True
