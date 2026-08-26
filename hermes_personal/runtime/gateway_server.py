from __future__ import annotations

import argparse
import hmac
import os
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI

from hermes_personal.application import (
    EventsAPI,
    HealthAPI,
    StaticBearerAuthenticator,
    create_application,
)
from hermes_personal.gateway.normalizers import ChannelTurnNormalizer
from hermes_personal.identity import IdentityRepository
from hermes_personal.observability.health import ComponentHealth, HealthReport
from hermes_personal.orchestration import AgentOutput, EventRepository, HermesTurnService
from hermes_personal.runtime.readiness import create_readiness_probe
from hermes_personal.runtime.startup import StartupCoordinator
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect


class _NullTranscript:
    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        return ()

    def append_user_turn(self, text: str) -> None:
        return None

    def append_event(self, event: Any) -> None:
        return None


class _NullTranscriptFactory:
    def for_session(self, session_id: str) -> _NullTranscript:
        return _NullTranscript()


class DevelopmentFakeAgent:
    """Deterministic local provider for development smoke tests only."""

    def run(self, request: Any, history: Any) -> Iterator[AgentOutput]:
        text = f"[fake-provider] Hermes received: {request.message}"
        yield AgentOutput("text_delta", {"text": text})
        yield AgentOutput("completed", {"text": text, "provider_mode": "fake"})


def create_configured_agent(session_id: str | None = None) -> Any:
    """Create the canonical upstream Hermes AIAgent wrapped in UpstreamAIAgentAdapter."""
    from run_agent import AIAgent
    from hermes_personal.orchestration.upstream_agent import UpstreamAIAgentAdapter

    agent = AIAgent(
        quiet_mode=True,
        session_id=session_id or "",
    )
    return UpstreamAIAgentAdapter(agent)


class SessionScopedAgentPool:
    """Manages session-scoped AIAgent instances keyed by (owner_id, session_id).

    Architecture Guarantees:
    - Single Brain: Delegates every conversation turn to public upstream AIAgent.run_conversation.
    - Prompt Caching: Associates a dedicated AIAgent instance per session, maintaining stable session_id.
    - Concurrency & State Isolation: Different sessions operate on independent AIAgent instances.
    - Clean Lifecycle: Closes and clears all agent instances on shutdown.
    """

    def __init__(
        self,
        agent_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._factory = agent_factory or (
            lambda owner_id, session_id: create_configured_agent(session_id=session_id)
        )
        self._agents: dict[tuple[str, str], Any] = {}
        self._lock = threading.Lock()

    def get_agent(self, owner_id: str, session_id: str) -> Any:
        key = (owner_id, session_id)
        with self._lock:
            if key not in self._agents:
                self._agents[key] = self._factory(owner_id, session_id)
            return self._agents[key]

    def run(
        self,
        request: Any,
        history: tuple[Mapping[str, Any], ...],
    ) -> Iterator[AgentOutput]:
        owner_id = getattr(request, "owner_id", None) or getattr(
            getattr(request, "principal", None), "owner_user_id", "default-owner"
        )
        session_id = getattr(request, "session_id", "default-session")
        agent = self.get_agent(owner_id, session_id)
        return agent.run(request, history)

    def close(self) -> None:
        with self._lock:
            for agent in self._agents.values():
                close_fn = getattr(agent, "close", None)
                if callable(close_fn):
                    try:
                        close_fn()
                    except Exception:
                        pass
            self._agents.clear()


def _ensure_identity(
    connection: sqlite3.Connection,
    owner_user_id: str,
    external_subject: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO global_user_identity
              (owner_user_id, display_name, created_at)
            VALUES (?, ?, ?)
            """,
            (owner_user_id, "Local Hermes Owner", now),
        )
        for channel in ("web", "omni"):
            existing = connection.execute(
                """
                SELECT owner_user_id FROM channel_identity
                WHERE channel = ? AND external_subject = ?
                """,
                (channel, external_subject),
            ).fetchone()
            if existing is not None and existing["owner_user_id"] != owner_user_id:
                raise RuntimeError(
                    f"{channel} subject is already linked to another Hermes owner"
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO channel_identity
                  (channel, external_subject, owner_user_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (channel, external_subject, owner_user_id, now),
            )


def _health_api() -> HealthAPI:
    report = StartupCoordinator().prepare()
    health_report = HealthReport.from_components(
        (ComponentHealth(name="gateway", required=True, status="healthy"),)
    )
    probe = create_readiness_probe(
        report,
        get_health_report=lambda: health_report,
        check_capability_snapshot=lambda: True,
        check_dependency_probes=lambda: True,
    )
    return HealthAPI(probe)


def create_gateway_application(
    *,
    database_path: Path,
    api_key: str,
    owner_user_id: str = "local-owner",
    external_subject: str = "local-owner",
    provider_mode: str = "configured",
    agent: Any | None = None,
) -> FastAPI:
    if not api_key:
        raise ValueError("HERMES_API_KEY is required")
    if provider_mode not in {"configured", "fake"}:
        raise ValueError(f"Unsupported provider mode: {provider_mode}")

    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(database_path)
    _ensure_identity(connection, owner_user_id, external_subject)
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    events = EventRepository(connection)
    if agent is None:
        agent = (
            DevelopmentFakeAgent()
            if provider_mode == "fake"
            else SessionScopedAgentPool()
        )
    service = HermesTurnService(
        identities,
        sessions,
        events,
        _NullTranscriptFactory(),
        agent,
    )
    validate_token = lambda token, owner: (
        owner == owner_user_id and hmac.compare_digest(token, api_key)
    )
    app = create_application(
        health_api=_health_api(),
        events_api=EventsAPI(events, auth_validator=validate_token),
        turn_service=service,
        turn_normalizers={
            "web": ChannelTurnNormalizer("web", identities, sessions),
            "omni": ChannelTurnNormalizer("omni", identities, sessions),
        },
        turn_authenticator=StaticBearerAuthenticator(
            api_key, owner_user_id, external_subject
        ),
    )

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, bool]:
        return {"ready": True}

    @app.on_event("shutdown")
    def _shutdown_gateway() -> None:
        if hasattr(agent, "close"):
            try:
                agent.close()
            except Exception:
                pass
        try:
            connection.close()
        except Exception:
            pass

    app.state.database_connection = connection
    app.router.add_event_handler("shutdown", connection.close)
    return app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes canonical Agent Turn gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8642)
    parser.add_argument("--provider-mode", choices=("configured", "fake"), default="configured")
    parser.add_argument("--db-path", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    api_key = os.environ.get("HERMES_API_KEY", "")
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    database_path = Path(args.db_path) if args.db_path else home / "hermes.db"
    app = create_gateway_application(
        database_path=database_path,
        api_key=api_key,
        owner_user_id=os.environ.get("HERMES_OWNER_ID", "local-owner"),
        external_subject=os.environ.get("HERMES_EXTERNAL_SUBJECT", "local-owner"),
        provider_mode=args.provider_mode,
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
