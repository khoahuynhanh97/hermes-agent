from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from hermes_personal.contracts import AgentTurnRequest
from hermes_personal.learning.retrieval import ApprovedLearningRetriever, RetrievedLearning


@dataclass(frozen=True)
class AgentContext:
    session_id: str
    owner_user_id: str
    history: tuple[Mapping[str, Any], ...]
    owner_preferences: tuple[RetrievedLearning, ...]
    approved_knowledge: tuple[RetrievedLearning, ...]
    approved_procedures: tuple[RetrievedLearning, ...]
    workflow_summary: str | None = None
    capability_summaries: tuple[str, ...] = ()

    def build_system_context(self) -> str:
        sections: list[str] = []

        if self.owner_preferences:
            pref_lines = [f"- {p.title}: {p.content}" for p in self.owner_preferences]
            sections.append("## Owner Preferences\n" + "\n".join(pref_lines))

        if self.approved_knowledge:
            know_lines = [f"### {k.title}\n{k.content}" for k in self.approved_knowledge]
            sections.append("## Approved Knowledge\n" + "\n\n".join(know_lines))

        if self.approved_procedures:
            proc_lines = [f"### {p.title}\n{p.content}" for p in self.approved_procedures]
            sections.append("## Approved Procedures\n" + "\n\n".join(proc_lines))

        if self.workflow_summary:
            sections.append(f"## Active Workflow\n{self.workflow_summary}")

        if self.capability_summaries:
            sections.append("## Available Capabilities\n" + "\n".join(f"- {c}" for c in self.capability_summaries))

        return "\n\n".join(sections)

    def assemble_history_messages(self) -> tuple[Mapping[str, Any], ...]:
        sys_context = self.build_system_context()
        if not sys_context:
            return self.history

        # Prepend system context if history doesn't already have it
        context_message = {
            "role": "system",
            "content": f"[Governed Personal Context]\n{sys_context}",
        }
        return (context_message,) + self.history


class AgentContextAssembler:
    """Assembles bounded AgentContext for upstream execution."""

    def __init__(self, retriever: ApprovedLearningRetriever) -> None:
        self.retriever = retriever

    def assemble(
        self,
        request: AgentTurnRequest,
        history: tuple[Mapping[str, Any], ...],
        workflow_summary: str | None = None,
        capability_summaries: tuple[str, ...] = (),
    ) -> AgentContext:
        owner_id = request.principal.owner_user_id

        preferences = self.retriever.retrieve(
            owner_user_id=owner_id,
            query=request.message,
            kind="preference",
            limit=5,
        )
        knowledge = self.retriever.retrieve(
            owner_user_id=owner_id,
            query=request.message,
            kind="knowledge",
            workflow_type=request.workflow_id,
            limit=3,
        )
        procedures = self.retriever.retrieve(
            owner_user_id=owner_id,
            query=request.message,
            kind="procedure",
            workflow_type=request.workflow_id,
            limit=2,
        )

        return AgentContext(
            session_id=request.session_id,
            owner_user_id=owner_id,
            history=history,
            owner_preferences=preferences,
            approved_knowledge=knowledge,
            approved_procedures=procedures,
            workflow_summary=workflow_summary,
            capability_summaries=capability_summaries,
        )
