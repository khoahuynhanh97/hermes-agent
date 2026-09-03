"""Knowledge edge capability MCP surface.

This module intentionally keeps only the MCP entry point thin. Durable
approval, candidate persistence, retrieval, and publication remain owned by
``hermes_personal.learning``. No second memory platform or conversation brain
is introduced here.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from hermes_personal.learning.models import (
    EvidenceRef,
    LearningCandidate,
    LearningKind,
)
from hermes_personal.learning.promotion import PromotionService
from hermes_personal.learning.repository import LearningRepository
from hermes_personal.learning.retrieval import ApprovedLearningRetriever
from hermes_personal.storage.sqlite import connect

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    try:
        from mcp.server import MCPServer as FastMCP
    except ImportError:
        FastMCP = None  # type: ignore[misc,assignment]

DEFAULT_OWNER_USER_ID = "default_user"


class KnowledgeEdgeCapability:
    """Approved-only knowledge edge capability.

    Knowledge candidates require explicit human review. Retrieval is restricted
    to approved entries. This owner never auto-approves unapproved knowledge.
    """

    def __init__(
        self,
        repository: LearningRepository,
        retriever: ApprovedLearningRetriever | None = None,
        promotion_service: PromotionService | None = None,
        default_owner_user_id: str = DEFAULT_OWNER_USER_ID,
    ) -> None:
        self._repository = repository
        self._retriever = retriever or ApprovedLearningRetriever(repository)
        self._promotion = promotion_service or PromotionService(repository)
        self._default_owner_user_id = default_owner_user_id

    def create_candidate(
        self,
        owner_user_id: str | None,
        title: str,
        content: str,
        kind: str = "knowledge",
        evidence: tuple[EvidenceRef, ...] | list[dict[str, Any]] | None = None,
        source_outcome_id: str | None = None,
    ) -> dict[str, Any]:
        bound_owner = owner_user_id or self._default_owner_user_id

        parsed_evidence: list[EvidenceRef] = []
        if evidence:
            for item in evidence:
                if isinstance(item, EvidenceRef):
                    parsed_evidence.append(item)
                elif isinstance(item, dict):
                    ev_id = item.get("evidence_id") or f"ev_{uuid.uuid4().hex[:12]}"
                    digest = item.get("digest") or ("sha256:" + hashlib.sha256(item.get("excerpt", "").encode("utf-8")).hexdigest())
                    parsed_evidence.append(
                        EvidenceRef(
                            evidence_id=ev_id,
                            source_type=item.get("source_type", "turn"),
                            source_id=item.get("source_id", source_outcome_id or "turn_context"),
                            digest=digest,
                            excerpt=item.get("excerpt", content[:200]),
                            polarity=item.get("polarity", "positive"),
                        )
                    )

        if not parsed_evidence:
            ev_id = f"ev_{uuid.uuid4().hex[:12]}"
            digest = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
            parsed_evidence.append(
                EvidenceRef(
                    evidence_id=ev_id,
                    source_type="turn",
                    source_id=source_outcome_id or "turn_context",
                    digest=digest,
                    excerpt=content[:200],
                    polarity="positive",
                )
            )

        candidate_id = f"cand_{uuid.uuid4().hex[:12]}"
        candidate = self._repository.create_candidate(
            LearningCandidate(
                candidate_id=candidate_id,
                owner_user_id=bound_owner,
                kind=kind,  # type: ignore[arg-type]
                title=title,
                content=content,
                evidence=tuple(parsed_evidence),
                source_outcome_id=source_outcome_id,
                status="draft",
            )
        )
        return {
            "candidate_id": candidate.candidate_id,
            "status": candidate.status,
            "kind": candidate.kind,
            "owner_user_id": candidate.owner_user_id,
        }

    def retrieve(
        self,
        owner_user_id: str | None,
        query: str = "",
        kind: str | None = None,
        limit: int = 5,
    ) -> tuple[Any, ...]:
        bound_owner = owner_user_id or self._default_owner_user_id
        parsed_kind = None
        if kind is not None:
            parsed_kind = LearningKind(kind)
        return self._retriever.retrieve(
            owner_user_id=bound_owner,
            query=query,
            kind=parsed_kind,
            limit=limit,
        )

    def request_promotion(
        self,
        candidate_id: str,
        evaluation: Any,
    ) -> dict[str, Any]:
        result = self._promotion.request_promotion(
            candidate=self._repository.get_candidate(candidate_id),  # type: ignore[arg-type]
            evaluation=evaluation,
        )
        return {
            "status": result.status,
            "approval_id": result.approval_id,
            "message": result.message,
            "version_id": result.version.version_id if result.version else None,
        }


def create_knowledge_mcp(
    capability: KnowledgeEdgeCapability | None = None,
) -> Any:
    """Create the Knowledge MCP server when FastMCP is available."""
    if FastMCP is None:
        raise RuntimeError("FastMCP is not installed; cannot create Knowledge MCP server")

    if capability is None:
        hermes_home = Path(get_hermes_home())
        db_path = hermes_home / "hermes_personal.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect(db_path)
        repository = LearningRepository(connection)
        capability = KnowledgeEdgeCapability(
            repository=repository,
            retriever=ApprovedLearningRetriever(repository),
            promotion_service=PromotionService(repository),
        )

    mcp = FastMCP("knowledge")

    @mcp.tool()
    def knowledge_candidate_create(
        title: str,
        content: str,
        owner_user_id: str | None = None,
        kind: str = "knowledge",
        source_outcome_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a knowledge candidate for human review."""
        return capability.create_candidate(
            owner_user_id=owner_user_id,
            title=title,
            content=content,
            kind=kind,
            source_outcome_id=source_outcome_id,
        )

    @mcp.tool()
    def knowledge_retrieve(
        query: str = "",
        owner_user_id: str | None = None,
        kind: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Retrieve approved knowledge entries only."""
        results = capability.retrieve(
            owner_user_id=owner_user_id,
            query=query,
            kind=kind,
            limit=limit,
        )
        return {
            "count": len(results),
            "items": [
                {
                    "version_id": item.version_id,
                    "candidate_id": item.candidate_id,
                    "kind": item.kind if isinstance(item.kind, str) else item.kind.value,
                    "title": item.title,
                    "content": item.content,
                    "score": item.score,
                }
                for item in results
            ],
        }

    return mcp


def main() -> None:
    """Run the Knowledge MCP server over stdio transport."""
    server = create_knowledge_mcp()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
