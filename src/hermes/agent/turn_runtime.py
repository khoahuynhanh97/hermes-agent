"""Neutral Agent Turn Runtime boundary for all channels."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from hermes.security.ingress import principal_scope
from hermes.security.principal import PrincipalContext


@dataclass(frozen=True)
class AgentTurnRequest:
    message: str
    principal: PrincipalContext
    platform: str = "cli"
    conversation_history: Tuple[Dict[str, Any], ...] = ()
    enabled_toolsets: Tuple[str, ...] = ()
    task_id: Optional[str] = None


@dataclass(frozen=True)
class AgentTurnResult:
    content: str
    messages: Tuple[Dict[str, Any], ...]
    usage: Dict[str, int]
    session_id: str
    completed: bool


class AgentTurnRuntime:
    """Channel-neutral turn execution wrapper over AIAgent and conversation_loop."""

    def __init__(self, agent_instance: Any = None):
        self.agent_instance = agent_instance

    def run(self, request: AgentTurnRequest) -> AgentTurnResult:
        """Run an Agent Turn wrapped in request.principal scope."""
        if self.agent_instance is None:
            from hermes.agent.runtime_agent import AIAgent
            agent = AIAgent()
        else:
            agent = self.agent_instance

        with principal_scope(request.principal):
            result = agent.run_conversation(
                user_message=request.message,
                conversation_history=list(request.conversation_history),
                task_id=request.task_id or request.principal.session_id,
            )

        return AgentTurnResult(
            content=result.get("content", ""),
            messages=tuple(result.get("messages", [])),
            usage=result.get("usage", {}),
            session_id=request.principal.session_id,
            completed=True,
        )
