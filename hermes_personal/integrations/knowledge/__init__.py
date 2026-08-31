"""Knowledge edge capability MCP surface.

This module intentionally keeps only the MCP entry point thin. Durable
approval, candidate persistence, retrieval, and publication remain owned by
``hermes_personal.learning``. No second memory platform or conversation brain
is introduced here.
"""

from __future__ import annotations

from typing import Any

from hermes_personal.learning.models import LearningKind
from hermes_personal.learning.promotion import PromotionService
from hermes_personal.learning.repository import LearningRepository
from hermes_personal.learning.retrieval import ApprovedLearningRetriever

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - optional dependency boundary
    FastMCP = None  # type: ignore[misc,assignment]


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
    ) -> None:
        self._repository = repository
        self._retriever = retriever or ApprovedLearningRetriever(repository)
        self._promotion = promotion_service or PromotionService(repository)

    def create_candidate(
        self,
        owner_user_id: str,
        title: str,
        content: str,
        kind: str = "knowledge",
        evidence: tuple[Any, ...] | None = None,
        source_outcome_id: str | None = None,
    ) -> dict:
        candidate = self._repository.create_candidate(
            self._repository.models.LearningCandidate(
                candidate_id=self._repository.models.generate_candidate_id(),
                owner_user_id=owner_user_id,
                kind=kind,
                title=title,
                content=content,
                evidence=evidence or (),
                source_outcome_id=source_outcome_id,
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
        owner_user_id: str,
        query: str = "",
        kind: str | None = None,
        limit: int = 5,
    ) -> tuple[Any, ...]:
        parsed_kind = None
        if kind is not None:
            parsed_kind = LearningKind(kind)
        return self._retriever.retrieve(
            owner_user_id=owner_user_id,
            query=query,
            kind=parsed_kind,
            limit=limit,
        )

    def request_promotion(
        self,
        candidate_id: str,
        evaluation: Any,
    ) -> dict:
        result = self._promotion.request_promotion(
            candidate=self._repository.get_candidate(candidate_id),
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
        from hermes_personal.storage.sqlite import connect
        from hermes_personal.learning.repository import LearningRepository
        from hermes_personal.learning.retrieval import ApprovedLearningRetriever
        connection = connect(":memory:")
        repository = LearningRepository(connection)
        capability = KnowledgeEdgeCapability(
            repository=repository,
            retriever=ApprovedLearningRetriever(repository),
        )

    mcp = FastMCP("knowledge")

    @mcp.tool()
    def knowledge_candidate_create(
        owner_user_id: str,
        title: str,
        content: str,
        kind: str = "knowledge",
        source_outcome_id: str | None = None,
    ) -> dict:
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
        owner_user_id: str,
        query: str = "",
        kind: str | None = None,
        limit: int = 5,
    ) -> dict:
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
                    "kind": item.kind.value,
                    "title": item.title,
                    "content": item.content,
                    "score": item.score,
                }
                for item in results
            ],
        }

    return mcp
