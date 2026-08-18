from __future__ import annotations

import uuid
from typing import Any

from hermes.domain.results import Result
from hermes.ports.knowledge_repository import KnowledgeRepository


class KnowledgeService:
    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    def propose(self, title: str, source: str, category: str = "general") -> Result[dict[str, Any]]:
        proposal: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "title": title,
            "source": source,
            "category": category,
            "status": "pending",
        }
        return self.repository.save(proposal)

    def approve(self, proposal_id: str) -> Result[dict[str, Any]]:
        proposal = self.repository.get(proposal_id)
        if not proposal.ok:
            return proposal
        if proposal.value.get("status") != "pending":
            return Result.failure("conflict", f"Proposal {proposal_id} is not pending")
        proposal.value["status"] = "approved"
        return self.repository.save(proposal.value)

    def reject(self, proposal_id: str) -> Result[None]:
        proposal = self.repository.get(proposal_id)
        if not proposal.ok:
            return Result.failure(proposal.error_code, proposal.message)
        proposal.value["status"] = "rejected"
        return self.repository.save(proposal.value)

    def search(self, query: str) -> Result[list[dict[str, Any]]]:
        return self.repository.search(query)

    def list_pending(self) -> Result[list[dict[str, Any]]]:
        return self.repository.list_by_status("pending")

    def list_approved(self) -> Result[list[dict[str, Any]]]:
        return self.repository.list_by_status("approved")