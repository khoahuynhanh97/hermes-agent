from __future__ import annotations

import argparse
import hmac
import logging
import os
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from hermes_personal.application import (
    EventsAPI,
    HealthAPI,
    StaticBearerAuthenticator,
    create_application,
    create_operator_command_handler,
)
from hermes_personal.capabilities import (
    CapabilityCatalogService,
    CapabilityPolicyEvaluator,
    CapabilitySnapshotRepository,
)
from hermes_personal.gateway.normalizers import ChannelTurnNormalizer
from hermes_personal.identity import IdentityRepository
from hermes_personal.observability.health import ComponentHealth, HealthReport
from hermes_personal.orchestration import AgentOutput, EventRepository, HermesTurnService
from hermes_personal.runtime.readiness import create_readiness_probe
from hermes_personal.runtime.startup import StartupCoordinator
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.budgets import BudgetRepository
from hermes_personal.workflows.outbox_repository import OutboxRepository


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


def _health_api(
    connection: sqlite3.Connection | None = None,
    outbox_repository: OutboxRepository | None = None,
    catalog_service: CapabilityCatalogService | None = None,
    snapshots: CapabilitySnapshotRepository | None = None,
    provider_mode: str = "configured",
) -> HealthAPI:
    if snapshots is None and connection is not None:
        snapshots = CapabilitySnapshotRepository(connection)

    def _run_migrations() -> None:
        if connection is not None:
            from hermes_personal.storage.sqlite import _migrate_schema

            _migrate_schema(connection)

    def _reclaim_leases() -> int:
        if outbox_repository is not None:
            return outbox_repository.reclaim_expired()
        return 0

    def _recover_workflows() -> tuple[int, int]:
        if connection is not None:
            from hermes_personal.workflows.recovery import WorkflowRecoveryService

            rec = WorkflowRecoveryService(connection)
            wfs = rec.recover_pending_workflows()
            return len(wfs), 0
        return 0, 0

    def _probe_db() -> bool:
        if connection is not None:
            try:
                cur = connection.cursor()
                cur.execute("SELECT 1")
                return True
            except Exception:
                return False
        return True

    def _activate_snapshot() -> None:
        if snapshots is None:
            return

        if provider_mode == "fake":
            active = snapshots.get_active()
            if active is not None:
                return
            # Explicit fake development mode: allow seeding test baseline
            from hermes_personal.capabilities.bindings import ImplementationBinding
            from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES

            bindings = tuple(
                ImplementationBinding(
                    capability_id=spec.capability_id,
                    wire_name=spec.capability_id.replace(".", "_"),
                    source="builtin",
                    provider=spec.owner,
                    implementation_version="1.0.0",
                    input_schema_version=spec.input_schema_version,
                    output_schema_version=spec.output_schema_version,
                    schema_digest=f"sha256:{spec.capability_id}",
                    health="healthy",
                )
                for spec in INITIAL_CAPABILITIES.values()
            )
            snapshots.save_and_activate(bindings)
        else:
            # Configured production mode:
            # Must verify against real tool registry — do NOT return early even if a fake/old snapshot exists in DB
            from hermes_personal.runtime.startup import (
                StartupErrorCode,
                StartupFailure,
                StartupStep,
            )

            if catalog_service is None or catalog_service.registry is None:
                raise StartupFailure(
                    StartupStep.CAPABILITY_SNAPSHOT_ACTIVATION,
                    "No catalog service or tool registry configured for capability discovery reload",
                    StartupErrorCode.CAPABILITY_ACTIVATION_FAILED,
                )

            try:
                catalog_service.reload()
            except Exception as exc:
                raise StartupFailure(
                    StartupStep.CAPABILITY_SNAPSHOT_ACTIVATION,
                    f"Configured capability discovery failed: {exc}",
                    StartupErrorCode.CAPABILITY_ACTIVATION_FAILED,
                ) from exc

    coordinator = StartupCoordinator(
        migration_runner=_run_migrations,
        lease_recovery=_reclaim_leases,
        workflow_recovery=_recover_workflows,
        snapshot_activator=_activate_snapshot,
        dependency_prober=_probe_db,
    )
    report = coordinator.prepare()
    health_report = HealthReport.from_components(
        (ComponentHealth(name="gateway", required=True, status="healthy"),)
    )

    def _check_snapshot_ready() -> bool:
        if snapshots is None:
            return False
        active = snapshots.get_active()
        if active is None:
            return False
        if provider_mode == "fake":
            return True
        if catalog_service is None or catalog_service.registry is None:
            return False
        return True

    probe = create_readiness_probe(
        report,
        get_health_report=lambda: health_report,
        check_capability_snapshot=_check_snapshot_ready,
        check_dependency_probes=_probe_db,
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
    tool_registry: Any | None = None,
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
    budget_repository = BudgetRepository(connection)
    evaluator = CapabilityPolicyEvaluator(budget_repository=budget_repository)
    snapshots = CapabilitySnapshotRepository(connection)
    catalog_service = CapabilityCatalogService(
        snapshot_repository=snapshots,
        policy_evaluator=evaluator,
        registry=tool_registry,
    )
    outbox_repository = OutboxRepository(connection)
    # NOTE: The gateway does NOT own outbox delivery.  The durable_worker process
    # is the sole OutboxDispatcher runner.  The gateway stores only the repository
    # reference for state inspection (e.g. health checks).
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
        catalog_service=catalog_service,
    )
    validate_token = lambda token, owner: (
        owner == owner_user_id and hmac.compare_digest(token, api_key)
    )
    cmd_handler = create_operator_command_handler(connection, provider_mode=provider_mode)
    health_api_instance = _health_api(
        connection=connection,
        outbox_repository=outbox_repository,
        catalog_service=catalog_service,
        snapshots=snapshots,
        provider_mode=provider_mode,
    )
    app = create_application(
        health_api=health_api_instance,
        events_api=EventsAPI(events, auth_validator=validate_token, command_handler=cmd_handler),
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
    def healthz() -> JSONResponse:
        status_code, body = health_api_instance.handle_ready()
        return JSONResponse(status_code=status_code, content=body)

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
    app.state.outbox_repository = outbox_repository
    app.state.outbox_dispatcher = None  # delivery owned by durable_worker process
    app.router.add_event_handler("shutdown", _shutdown_gateway)
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
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    database_path = Path(args.db_path) if args.db_path else home / "hermes.db"

    tool_registry = None
    if args.provider_mode == "configured":
        from tools.registry import registry

        tool_registry = registry

    app = create_gateway_application(
        database_path=database_path,
        api_key=api_key,
        owner_user_id=os.environ.get("HERMES_OWNER_ID", "local-owner"),
        external_subject=os.environ.get("HERMES_EXTERNAL_SUBJECT", "local-owner"),
        provider_mode=args.provider_mode,
        tool_registry=tool_registry,
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
