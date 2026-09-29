from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.envelope import OutboxEnvelope
from hermes_personal.workflows.outbox_dispatcher import (
    DispatchReport,
    FatalPersistenceError,
    OutboxDispatcher,
)
from hermes_personal.workflows.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)


def run_worker(
    db_path: str | Path,
    poll_interval: float = 1.0,
    stop_event: Optional[threading.Event] = None,
    topic_handlers: Optional[Dict[str, Callable[[OutboxEnvelope], None]]] = None,
    delivery_fn: Optional[Callable[[str, str], None]] = None,
    worker_id: Optional[str] = None,
    tool_registry: Any | None = None,
    provider_mode: Optional[str] = None,
    render_poll_timeout: float = 60.0,
    render_poll_interval: float = 0.5,
    once: bool = False,
    batch_size: int = 1,
    workflow_id_prefix: str | None = None,
    workflow_ids: list[str] | None = None,
) -> DispatchReport | None:
    """Run the durable outbox worker loop."""
    if stop_event is None:
        stop_event = threading.Event()

    from hermes_personal.product_video.provider_runtime import (
        resolve_polling_setting,
        resolve_provider_mode,
        validate_polling_setting,
        validate_provider_mode,
    )

    _provider_mode = resolve_provider_mode(
        cli_arg=provider_mode,
        env_val=os.environ.get("HERMES_PROVIDER_MODE"),
    )
    _render_poll_timeout = validate_polling_setting("render_poll_timeout", render_poll_timeout, 60.0)
    _render_poll_interval = validate_polling_setting("render_poll_interval", render_poll_interval, 0.5)

    if _provider_mode == "configured":
        try:
            from tools.mcp_tool import discover_mcp_tools
            discover_mcp_tools()
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP tool discovery failed in run_worker: %s", exc)

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    repo = OutboxRepository(connection)
    _worker_id = worker_id or f"durable-worker-{os.getpid()}"

    from hermes_personal.workflows.budgets import BudgetPolicy, init_default_engine
    init_default_engine(
        policy=BudgetPolicy(max_total=100000, per_channel={"video_factory": 50000, "telegram": 10000, "default": 10000}),
        connection=connection,
        owner_user_id="default-owner",
    )

    if topic_handlers is None and delivery_fn is None:
        from hermes_personal.product_video.handlers import (
            create_configured_creative_generator,
            create_product_video_topic_handlers,
        )
        from hermes_personal.workflows.engine import WorkflowEngine
        from hermes_personal.workflows.repository import WorkflowRepository

        wf_repo = WorkflowRepository(connection)
        wf_engine = WorkflowEngine(wf_repo)
        creative_generator = (
            create_configured_creative_generator()
            if _provider_mode == "configured"
            else None
        )
        topic_handlers = create_product_video_topic_handlers(
            workflow_engine=wf_engine,
            workflow_repository=wf_repo,
            tool_registry=tool_registry,
            provider_mode=_provider_mode,
            poll_timeout=_render_poll_timeout,
            poll_interval=_render_poll_interval,
            creative_generator=creative_generator,
        )
    # Scale lease duration so it comfortably covers polling duration + buffer (prevents stale ACK failure)
    # A storyboard job can make several sequential keyframe calls and then run
    # image QC before it ACKs. Renewals below keep this bounded lease alive.
    lease_duration = max(300.0, _render_poll_timeout + 60.0)
    dispatcher = OutboxDispatcher(
        repository=repo,
        delivery_fn=delivery_fn,
        worker_id=_worker_id,
        lease_duration_seconds=lease_duration,
        topic_handlers=topic_handlers,
    )

    logger.info("Durable worker started (db=%s, worker_id=%s, provider_mode=%s, lease_duration=%.1fs)", db_path, _worker_id, _provider_mode, lease_duration)
    try:
        if once:
            dispatcher.reclaim_expired()
            return dispatcher.process_batch(
                batch_size=batch_size,
                workflow_id_prefix=workflow_id_prefix,
                workflow_ids=workflow_ids,
            )
        while not stop_event.is_set():
            try:
                dispatcher.reclaim_expired()
                dispatcher.process_batch(batch_size=1)
            except FatalPersistenceError as exc:
                logger.error("Fatal persistence error in durable worker: %s", exc, exc_info=True)
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Error in durable worker polling loop: %s", exc, exc_info=True)
            stop_event.wait(poll_interval)
    finally:
        logger.info("Durable worker shutting down, closing database connection...")
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes durable background worker")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database file")
    parser.add_argument(
        "--poll-interval", type=float, default=1.0, help="Worker outbox poll interval in seconds"
    )
    parser.add_argument(
        "--provider-mode",
        default=None,
        help="Provider mode ('configured' for live MCP/provider resolution, 'fake' for offline deterministic test). Defaults to config.yaml value.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one eligible batch and exit",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Maximum outbox rows processed per batch",
    )
    parser.add_argument(
        "--workflow-id-prefix",
        default=None,
        help="Only process workflows whose IDs start with this value",
    )
    parser.add_argument(
        "--render-poll-timeout",
        type=float,
        default=None,
        help="Video render status polling timeout in seconds",
    )
    parser.add_argument(
        "--render-poll-interval",
        type=float,
        default=None,
        help="Video render status polling interval in seconds",
    )
    args = parser.parse_args(argv)
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    db_path = Path(args.db_path) if args.db_path else home / "hermes.db"

    # Bootstrap configuration and environment secrets
    try:
        from hermes_cli.env_loader import load_hermes_dotenv
        load_hermes_dotenv(hermes_home=home)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to load hermes dotenv: %s", exc)

    try:
        from hermes_cli.config import load_config
        config = load_config()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to load hermes config: %s", exc)
        config = {}

    from hermes_personal.product_video.provider_runtime import (
        resolve_polling_setting,
        resolve_provider_mode,
    )

    resolved_provider_mode = resolve_provider_mode(
        cli_arg=args.provider_mode,
        config=config,
        env_val=os.environ.get("HERMES_PROVIDER_MODE"),
    )

    vf_config = config.get("video_factory", {}) if isinstance(config.get("video_factory"), dict) else (config.get("workflows", {}) if isinstance(config.get("workflows"), dict) else {})
    render_poll_timeout = resolve_polling_setting(
        "polling_timeout_seconds",
        cli_val=args.render_poll_timeout,
        cfg_val=vf_config.get("polling_timeout_seconds"),
        default=60.0,
    )
    render_poll_interval = resolve_polling_setting(
        "polling_interval_seconds",
        cli_val=args.render_poll_interval,
        cfg_val=vf_config.get("polling_interval_seconds"),
        default=0.5,
    )

    # Initialize MCP tool discovery if running in configured mode
    if resolved_provider_mode == "configured":
        try:
            from tools.mcp_tool import discover_mcp_tools
            discover_mcp_tools()
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP tool discovery failed on worker startup: %s", exc)

    stop_event = threading.Event()

    def _signal_handler(signum: int, frame: Any) -> None:
        logger.info("Received signal %s, stopping durable worker...", signum)
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except (ValueError, AttributeError):
        pass

    try:
        report = run_worker(
            db_path=db_path,
            poll_interval=args.poll_interval,
            stop_event=stop_event,
            provider_mode=resolved_provider_mode,
            render_poll_timeout=render_poll_timeout,
            render_poll_interval=render_poll_interval,
            once=args.once,
            batch_size=args.batch_size,
            workflow_id_prefix=args.workflow_id_prefix,
        )
    finally:
        if resolved_provider_mode == "configured":
            try:
                from tools.mcp_tool import shutdown_mcp_servers
                shutdown_mcp_servers()
            except Exception as exc:  # noqa: BLE001
                logger.debug("MCP shutdown failed: %s", exc)
    if isinstance(report, DispatchReport):
        logger.info(
            "One-shot worker result: claimed=%d succeeded=%d failed=%d quarantined=%d stale=%d",
            report.claimed,
            report.succeeded,
            report.failed,
            report.quarantined,
            report.stale,
        )
        if report.failed or report.quarantined or report.stale:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
