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


VALID_LEARNING_KINDS = {"preference", "knowledge", "procedure"}


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
        approval_service: Any | None = None,
    ) -> None:
        self._repository = repository
        self._retriever = retriever or ApprovedLearningRetriever(repository)
        self._approval_service = approval_service
        self._promotion = promotion_service or PromotionService(
            repository, approval_service=approval_service
        )
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
        bound_owner = self._default_owner_user_id
        if owner_user_id and owner_user_id.strip() and owner_user_id.strip() != bound_owner:
            raise ValueError(f"Owner mismatch: requested owner '{owner_user_id}' does not match bound session owner '{bound_owner}'")
        if kind not in VALID_LEARNING_KINDS:
            raise ValueError(f"Invalid learning kind: {kind!r}. Must be one of {sorted(VALID_LEARNING_KINDS)}")

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
            # Content hash without independent source is marked as unverified provenance
            digest = "unverified:sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
            parsed_evidence.append(
                EvidenceRef(
                    evidence_id=ev_id,
                    source_type="unverified",
                    source_id=source_outcome_id or "missing_provenance",
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

        # Auto-evaluate and request promotion
        from hermes_personal.learning.evaluator import CandidateEvaluator
        evaluator = CandidateEvaluator()
        task_outcome = None
        if source_outcome_id:
            task_outcome = self._repository.get_task_outcome(source_outcome_id)
        evaluation = evaluator.evaluate(candidate, source_outcome=task_outcome)

        try:
            promo_result = self._promotion.request_promotion(candidate, evaluation)
            return {
                "candidate_id": candidate.candidate_id,
                "status": promo_result.status,
                "kind": candidate.kind,
                "owner_user_id": candidate.owner_user_id,
                "approval_id": promo_result.approval_id,
                "message": promo_result.message,
            }
        except Exception:
            pass
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
        bound_owner = self._default_owner_user_id
        if owner_user_id and owner_user_id.strip() and owner_user_id.strip() != bound_owner:
            raise ValueError(f"Owner mismatch: requested owner '{owner_user_id}' does not match bound session owner '{bound_owner}'")
        parsed_kind = None
        if kind is not None:
            if kind not in VALID_LEARNING_KINDS:
                raise ValueError(f"Invalid learning kind: {kind!r}. Must be one of {sorted(VALID_LEARNING_KINDS)}")
            parsed_kind = kind  # type: ignore[assignment]
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

    def approve_candidate(
        self,
        candidate_id: str,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Approve a pending knowledge candidate via the approval service.
        
        This completes the HITL gate: the candidate's status changes to 'approved'
        and an active learning version is created.
        """
        bound_owner = self._default_owner_user_id
        if owner_user_id and owner_user_id.strip() and owner_user_id.strip() != bound_owner:
            raise ValueError(
                f"Owner mismatch: requested owner '{owner_user_id}' does not match "
                f"bound session owner '{bound_owner}'"
            )
        
        cand = self._repository.get_candidate(candidate_id)
        if not cand:
            raise ValueError(f"Candidate '{candidate_id}' not found")
        if cand.owner_user_id != bound_owner:
            raise ValueError("Candidate does not belong to the session owner")
        if cand.status not in ("pending_approval", "evaluated", "draft"):
            raise ValueError(f"Candidate status '{cand.status}' is not approvable")
        
        if self._approval_service is None:
            raise ValueError("Approval service is not configured")
        
        # Find the pending approval request for this candidate
        # If no approval request exists yet, create one and immediately approve it
        from hermes_personal.workflows.approvals import ApprovalStatus
        
        # Search for existing pending approval
        approval_id = None
        try:
            # Query all pending approvals to find one matching this candidate
            cur = self._approval_service.conn.cursor()
            cur.execute(
                "SELECT request_id, payload_json FROM approval_request WHERE status = ?",
                (ApprovalStatus.PENDING.value,),
            )
            import json
            for row in cur.fetchall():
                payload = json.loads(row["payload_json"] or "{}")
                if payload.get("candidate_id") == candidate_id:
                    approval_id = row["request_id"]
                    break
        except Exception:
            pass
        
        if approval_id is None:
            # Create an approval request and immediately approve it (operator-initiated)
            payload = {
                "action": "promote_learning",
                "owner_user_id": bound_owner,
                "candidate_id": candidate_id,
                "kind": cand.kind.value if hasattr(cand.kind, "value") else cand.kind,
                "title": cand.title,
                "content": cand.content,
                "content_digest": cand.compute_digest(),
                "expected_version": max(
                    (v.version for v in self._repository.get_versions_for_candidate(candidate_id)),
                    default=0,
                ) + 1,
            }
            approval_id = self._approval_service.submit_request(payload)
        
        # Approve the request
        self._approval_service.approve(approval_id)
        
        # Now promote through PromotionService
        try:
            version = self._promotion.approve_promotion(
                approval_id=approval_id,
                owner_user_id=bound_owner,
                candidate_id=candidate_id,
            )
            return {
                "status": "approved",
                "candidate_id": candidate_id,
                "version_id": version.version_id,
                "version": version.version,
                "message": f"Knowledge '{cand.title}' approved and active",
            }
        except Exception as e:
            return {
                "status": "error",
                "candidate_id": candidate_id,
                "message": str(e),
            }

    def reject_candidate(
        self,
        candidate_id: str,
        owner_user_id: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Reject a pending knowledge candidate."""
        bound_owner = self._default_owner_user_id
        if owner_user_id and owner_user_id.strip() and owner_user_id.strip() != bound_owner:
            raise ValueError(
                f"Owner mismatch: requested owner '{owner_user_id}' does not match "
                f"bound session owner '{bound_owner}'"
            )
        
        cand = self._repository.get_candidate(candidate_id)
        if not cand:
            raise ValueError(f"Candidate '{candidate_id}' not found")
        if cand.owner_user_id != bound_owner:
            raise ValueError("Candidate does not belong to the session owner")
        
        self._repository.update_candidate_status(candidate_id, "rejected")
        
        # Also reject any pending approval requests
        if self._approval_service is not None:
            try:
                from hermes_personal.workflows.approvals import ApprovalStatus
                import json
                cur = self._approval_service.conn.cursor()
                cur.execute(
                    "SELECT request_id, payload_json FROM approval_request WHERE status = ?",
                    (ApprovalStatus.PENDING.value,),
                )
                for row in cur.fetchall():
                    payload = json.loads(row["payload_json"] or "{}")
                    if payload.get("candidate_id") == candidate_id:
                        self._approval_service.reject(row["request_id"])
            except Exception:
                pass
        
        return {
            "status": "rejected",
            "candidate_id": candidate_id,
            "reason": reason or "Rejected by owner",
        }


def create_knowledge_mcp(
    capability: KnowledgeEdgeCapability | None = None,
) -> Any:
    """Create the Knowledge MCP server when FastMCP is available."""
    if FastMCP is None:
        raise RuntimeError("FastMCP is not installed; cannot create Knowledge MCP server")

    if capability is None:
        import os

        hermes_home = Path(get_hermes_home())
        db_path = hermes_home / "hermes_personal.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect(db_path)
        repository = LearningRepository(connection)
        bound_owner = os.environ.get("HERMES_OWNER_ID", DEFAULT_OWNER_USER_ID)

        from hermes_personal.workflows.approvals import ApprovalService
        approval_service = ApprovalService(connection)

        capability = KnowledgeEdgeCapability(
            repository=repository,
            retriever=ApprovedLearningRetriever(repository),
            promotion_service=PromotionService(repository, approval_service=approval_service),
            default_owner_user_id=bound_owner,
            approval_service=approval_service,
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

    @mcp.tool()
    def knowledge_candidate_approve(
        candidate_id: str,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Approve a pending knowledge candidate. Completes the human-in-the-loop gate."""
        return capability.approve_candidate(
            candidate_id=candidate_id,
            owner_user_id=owner_user_id,
        )

    @mcp.tool()
    def knowledge_candidate_reject(
        candidate_id: str,
        owner_user_id: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Reject a pending knowledge candidate."""
        return capability.reject_candidate(
            candidate_id=candidate_id,
            owner_user_id=owner_user_id,
            reason=reason,
        )

    return mcp


def main() -> None:
    """Run the Knowledge MCP server over stdio transport."""
    server = create_knowledge_mcp()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
