from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from hermes_personal.learning.models import LearningKind
from hermes_personal.learning.repository import LearningRepository


@dataclass(frozen=True)
class RetrievedLearning:
    version_id: str
    candidate_id: str
    owner_user_id: str
    kind: LearningKind
    title: str
    content: str
    score: float
    digest: str


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


class ApprovedLearningRetriever:
    """Owner-isolated retriever for approved active learning versions."""

    def __init__(self, repository: LearningRepository) -> None:
        self.repository = repository

    def retrieve(
        self,
        owner_user_id: str,
        query: str = "",
        kind: LearningKind | None = None,
        workflow_type: str | None = None,
        limit: int = 5,
    ) -> tuple[RetrievedLearning, ...]:
        active_versions = self.repository.get_active_versions_for_owner(owner_user_id, kind=kind)
        if not active_versions:
            return ()

        query_tokens = _tokenize(query)
        scored_items: list[tuple[float, str, RetrievedLearning]] = []

        for v in active_versions:
            # Enforce strict owner isolation and active status
            if v.owner_user_id != owner_user_id or v.status != "active":
                continue

            cand = self.repository.get_candidate(v.candidate_id)
            # Strict approved-only check: draft, evaluated, pending_approval, rejected are excluded
            if not cand or cand.status != "approved" or cand.owner_user_id != owner_user_id:
                continue

            title_tokens = _tokenize(cand.title)
            content_tokens = _tokenize(v.content)


            score = 0.0
            if query_tokens:
                title_overlap = len(query_tokens & title_tokens) / max(len(query_tokens), 1)
                content_overlap = len(query_tokens & content_tokens) / max(len(query_tokens), 1)
                score = (2.0 * title_overlap) + (1.0 * content_overlap)

            if workflow_type:
                wf_lower = workflow_type.lower()
                if wf_lower in cand.title.lower() or wf_lower in v.content.lower():
                    score += 0.5

            # Preferences have baseline relevance for owner turns if not strictly irrelevant
            if cand.kind == "preference":
                if not query_tokens:
                    score = 1.0
                else:
                    score += 0.2

            if score > 0.0:
                retrieved = RetrievedLearning(
                    version_id=v.version_id,
                    candidate_id=v.candidate_id,
                    owner_user_id=v.owner_user_id,
                    kind=cand.kind,
                    title=cand.title,
                    content=v.content,
                    score=score,
                    digest=v.digest,
                )
                scored_items.append((score, v.version_id, retrieved))

        # Sort by score DESC, version_id DESC for stable deterministic ranking
        scored_items.sort(key=lambda item: (item[0], item[1]), reverse=True)
        results = [item[2] for item in scored_items[:limit]]
        return tuple(results)
