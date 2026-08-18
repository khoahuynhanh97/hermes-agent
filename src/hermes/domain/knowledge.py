"""hermes/domain/knowledge.py — Domain models for the Knowledge Store.

Defines the core data structures used across all knowledge-related
operations: ingestion, approval workflow, and context injection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class LessonStatus(str, Enum):
    """Lifecycle status of a knowledge entry."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ApprovalEvent:
    """A single event in the approval history of a knowledge entry."""
    status: str
    at: str
    actor: Optional[str] = None
    mode: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class KnowledgeEntry:
    """A single lesson or piece of knowledge stored by Hermes.

    This is the canonical representation shared across:
      - JSON file store (unified_index.json)
      - SQLite store (hermes.db)
      - Telegram Bot display
      - Script generation context injection
    """
    id: str
    slug: str
    title: str
    status: LessonStatus = LessonStatus.PENDING

    # Source info
    source_url: str = ""
    platform: str = "unknown"
    category: str = "General"
    source: str = "telegram_job"

    # Content analysis
    hook_type: str = ""
    cta_style: str = ""
    voice_tone: str = ""
    key_lessons: list[str] = field(default_factory=list)

    # Timestamps
    learned_at: str = field(default_factory=lambda: datetime.now().isoformat())
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None

    # Approval metadata
    approved_by: Optional[str] = None
    approval_mode: Optional[str] = None
    rejected_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    approval_history: list[ApprovalEvent] = field(default_factory=list)

    # File references
    detail_file: str = ""
    job_output_dir: str = ""

    # Ownership
    owner_user_id: Optional[str] = None

    # Re-analysis flag
    needs_reanalysis: bool = False


@dataclass
class KnowledgeDetail:
    """Extended detail payload stored in a separate JSON file per entry.

    Contains the deep analysis results from Gemini Vision or
    other analysis pipelines.
    """
    summary: str = ""
    deep_analysis: str = ""
    source_summary: str = ""
    tools_and_concepts: str = ""
    workflow_steps: str = ""
    hermes_applications: str = ""
    how_to_use_in_hermes: str = ""

    # Structured data
    search_keywords: list[str] = field(default_factory=list)
    repositories: list[dict] = field(default_factory=list)
    ai_tools_or_skills: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)

    # Analysis metadata
    analysis_source: str = ""
    confidence: str = ""
    lesson_type: str = ""
    hook_type: str = ""
    cta_style: str = ""
    voice_tone: str = ""
