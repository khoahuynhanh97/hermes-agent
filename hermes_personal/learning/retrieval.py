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
    evidence_excerpt: str = ""
    source_ref: str = ""
    created_at: str = ""


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


class ApprovedLearningRetriever:
    """Owner-isolated retriever for approved active learning versions.

    Uses FTS5 as the primary retrieval method with token-overlap as fallback.
    Results are merged with FTS5 matches weighted higher.
    """

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
        scored_items: dict[str, tuple[float, RetrievedLearning]] = {}

        # --- Phase 1: FTS5 search (primary) ---
        if query.strip():
            fts_results = self.repository.search_fts(
                query, owner_user_id, kind=kind, limit=limit * 2
            )
            for candidate_id, version_id, title, snippet, rank in fts_results:
                version = self.repository.get_version(version_id)
                cand = self.repository.get_candidate(candidate_id)
                if not version or not cand:
                    continue
                if cand.status != "approved" or version.status != "active":
                    continue
                if version.owner_user_id != owner_user_id:
                    continue

                # FTS5 rank is negative (closer to 0 = better match)
                # Normalize to 0-3 range with higher = better
                fts_score = max(0.0, 3.0 + rank)  # rank is typically -0.x to -3.x

                # Fetch evidence for provenance
                evidence_excerpt = ""
                source_ref = ""
                evidence_list = self.repository.get_evidence_for_candidate(candidate_id)
                if evidence_list:
                    evidence_excerpt = evidence_list[0].excerpt[:200]
                    source_ref = evidence_list[0].source_id

                item = RetrievedLearning(
                    version_id=version_id,
                    candidate_id=candidate_id,
                    owner_user_id=owner_user_id,
                    kind=cand.kind,
                    title=title,
                    content=version.content,
                    score=fts_score,
                    digest=version.digest,
                    evidence_excerpt=evidence_excerpt,
                    source_ref=source_ref,
                    created_at=version.created_at,
                )
                scored_items[version_id] = (fts_score, item)

        # --- Phase 2: Token-overlap fallback ---
        active_versions = self.repository.get_active_versions_for_owner(
            owner_user_id, kind=kind
        )
        query_tokens = _tokenize(query)

        for v in active_versions:
            if v.owner_user_id != owner_user_id or v.status != "active":
                continue

            cand = self.repository.get_candidate(v.candidate_id)
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

            if cand.kind == "preference":
                if not query_tokens:
                    score = 1.0
                else:
                    score += 0.2

            if score > 0.0 and v.version_id not in scored_items:
                evidence_excerpt = ""
                source_ref = ""
                evidence_list = self.repository.get_evidence_for_candidate(v.candidate_id)
                if evidence_list:
                    evidence_excerpt = evidence_list[0].excerpt[:200]
                    source_ref = evidence_list[0].source_id

                item = RetrievedLearning(
                    version_id=v.version_id,
                    candidate_id=v.candidate_id,
                    owner_user_id=v.owner_user_id,
                    kind=cand.kind,
                    title=cand.title,
                    content=v.content,
                    score=score,
                    digest=v.digest,
                    evidence_excerpt=evidence_excerpt,
                    source_ref=source_ref,
                    created_at=v.created_at,
                )
                scored_items[v.version_id] = (score, item)
            elif score > 0.0 and v.version_id in scored_items:
                # Merge: keep higher score
                existing_score, existing_item = scored_items[v.version_id]
                if score > existing_score:
                    scored_items[v.version_id] = (score, existing_item)

        # Sort by score DESC, version_id DESC for stable ranking
        sorted_items = sorted(
            scored_items.values(),
            key=lambda item: (item[0], item[1].version_id),
            reverse=True,
        )
        results = [item[1] for item in sorted_items[:limit]]
        return tuple(results)
