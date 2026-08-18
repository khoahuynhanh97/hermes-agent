"""hermes/domain/project.py — Domain models for Projects, Workflows & Assets.

Canonical data structures for project management, video production
workflows, and asset tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ProjectStatus(str, Enum):
    """Project lifecycle status."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"


class WorkflowStepStatus(str, Enum):
    """Status of a single step within a workflow."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Project:
    """A content production project managed by Hermes.

    Each project typically represents one video or content piece,
    containing its script, assets, and production workflow.
    """
    id: str
    name: str
    filesystem_root: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True


@dataclass
class Workflow:
    """A production workflow attached to a project.

    Contains ordered steps for producing content
    (e.g., script → storyboard → render → publish).
    """
    id: str
    project_id: str
    name: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class WorkflowStep:
    """A single step within a production workflow."""
    id: str
    workflow_id: str
    name: str
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    content: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Asset:
    """A media asset (image, video, audio) attached to a project."""
    id: str
    project_id: str
    name: str
    file_path: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
