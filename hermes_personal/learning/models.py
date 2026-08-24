from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

LearningKind = Literal["preference", "knowledge", "procedure"]
CandidateStatus = Literal["draft", "evaluated", "pending_approval", "approved", "rejected"]
VersionStatus = Literal["active", "revoked", "superseded"]
TaskOutcomeStatus = Literal["success", "failure", "cancelled"]


class LearningError(Exception):
    """Base error for learning operations."""


class InvalidCandidate(LearningError):
    """Raised when candidate fails validation."""


class InvalidVersion(LearningError):
    """Raised when version fails validation."""


class LearningRepositoryError(LearningError):
    """Raised on repository errors."""


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_type: Literal["turn", "workflow", "artifact", "feedback", "tool_trace"]
    source_id: str
    digest: str
    excerpt: str
    polarity: Literal["positive", "negative"] = "positive"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class TaskOutcome:
    outcome_id: str
    source_type: str
    source_id: str
    status: TaskOutcomeStatus
    details: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class LearningCandidate:
    candidate_id: str
    owner_user_id: str
    kind: LearningKind
    title: str
    content: str
    evidence: tuple[EvidenceRef, ...] = ()
    source_outcome_id: str | None = None
    status: CandidateStatus = "draft"
    digest: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_digest(self) -> str:
        payload = f"{self.kind}:{self.title}:{self.content}".encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class LearningVersion:
    version_id: str
    candidate_id: str
    owner_user_id: str
    version: int
    content: str
    digest: str
    status: VersionStatus = "active"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class LearningEvent:
    event_id: str
    candidate_id: str
    event_type: str
    payload_json: str
    version_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
