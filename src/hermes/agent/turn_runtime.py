"""Neutral Agent Turn Runtime boundary for all channels."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

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

    def __init__(
        self,
        agent_instance: Any = None,
        agent_factory: Optional[Callable[[AgentTurnRequest], Any]] = None,
    ):
        if agent_instance is not None and agent_factory is not None:
            raise ValueError("Pass either agent_instance or agent_factory, not both")
        self.agent_instance = agent_instance
        self.agent_factory = agent_factory

    @staticmethod
    def _default_agent_factory(request: AgentTurnRequest) -> Any:
        import logging
        from hermes.agent.runtime_agent import AIAgent
        from hermes.channels.cli.mcp_startup import ensure_mcp_discovery_before_agent_build

        logger = logging.getLogger("hermes.agent.turn_runtime")
        ensure_mcp_discovery_before_agent_build(
            logger=logger,
            single_query=True,
            thread_name="agent-turn-mcp-discovery",
        )

        kwargs: Dict[str, Any] = {
            "model": os.environ.get("HERMES_INFERENCE_MODEL") or "reason_combo",
            "quiet_mode": True,
            "platform": request.platform,
            "session_id": request.principal.session_id,
            "user_id": request.principal.actor_id,
            "chat_id": request.principal.owner_user_id,
            "gateway_session_key": request.principal.session_id,
        }
        if request.enabled_toolsets:
            kwargs["enabled_toolsets"] = list(request.enabled_toolsets)
        return AIAgent(**kwargs)

    def run(self, request: AgentTurnRequest) -> AgentTurnResult:
        """Run an Agent Turn wrapped in request.principal scope."""
        owns_agent = self.agent_instance is None
        factory = self.agent_factory or self._default_agent_factory
        agent = self.agent_instance if self.agent_instance is not None else factory(request)

        try:
            with principal_scope(request.principal):
                result = agent.run_conversation(
                    user_message=request.message,
                    conversation_history=list(request.conversation_history),
                    task_id=request.task_id or request.principal.session_id,
                )
        finally:
            if owns_agent:
                close = getattr(agent, "close", None)
                if callable(close):
                    close()

        content = result.get("final_response") or result.get("content") or ""
        completed = not bool(result.get("error")) and not bool(result.get("interrupted"))

        return AgentTurnResult(
            content=str(content),
            messages=tuple(result.get("messages") or ()),
            usage=dict(result.get("usage") or {}),
            session_id=request.principal.session_id,
            completed=completed,
        )
