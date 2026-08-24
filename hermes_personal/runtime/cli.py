from __future__ import annotations

import argparse
import os
import re
import signal
import sys
from pathlib import Path

from hermes_personal.observability.redaction import redact
from hermes_personal.runtime.config import RuntimeConfig, RuntimeConfigError
from hermes_personal.runtime.processes import build_process_topology
from hermes_personal.runtime.startup import StartupCoordinator
from hermes_personal.runtime.supervisor import DefaultProcessRunner, Supervisor

DEFAULT_CLI_VALUE_FINGERPRINTS = (
    re.compile(r"sk-[a-zA-Z0-9_\-]+"),
    re.compile(r"ghp_[a-zA-Z0-9_\-]+"),
    re.compile(r"bot[0-9]+:[a-zA-Z0-9_\-]+"),
)


def setup_start_parser(subparser: argparse.ArgumentParser) -> None:
    """Setup CLI parser arguments for hermes start."""
    subparser.add_argument(
        "--mode",
        choices=["development", "production"],
        default="development",
        help="Runtime mode (development|production)",
    )
    subparser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml file",
    )
    subparser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Do not automatically open browser on startup",
    )


def handle_start(args: argparse.Namespace) -> int:
    """Execute hermes start command: validate config, run startup sequence, and supervise processes."""
    mode = getattr(args, "mode", "development")
    config_path = getattr(args, "config", None)
    repo_root = Path.cwd()

    try:
        if config_path:
            config = RuntimeConfig.from_file(
                config_path=config_path,
                mode=mode,
                repo_root=repo_root,
            )
        else:
            config = RuntimeConfig(
                mode=mode,
                repo_root=repo_root,
            )
    except RuntimeConfigError as ex:
        print(f"Configuration validation error: {ex}", file=sys.stderr)
        return 1

    # 1. Startup & Recovery Coordination
    coordinator = StartupCoordinator(
        config=config,
        env=dict(os.environ),
    )
    report = coordinator.prepare()

    if not report.is_ready:
        failing_step = report.steps[-1].name if report.steps else "unknown"
        failure_code = report.failure_code or "STARTUP_FAILED"
        redacted_details = redact(report.as_dict(), value_fingerprints=DEFAULT_CLI_VALUE_FINGERPRINTS)
        print(f"Startup readiness failed at step '{failing_step}' [{failure_code}]", file=sys.stderr)
        print(f"Startup details: {redacted_details}", file=sys.stderr)
        return 1

    print(f"Hermes runtime ready ({report.total_latency_ms:.1f}ms). Starting process supervision...")

    # 2. Build Process Topology & Run Supervisor
    try:
        specs = build_process_topology(config)
    except Exception as ex:
        print(f"Process topology error: {ex}", file=sys.stderr)
        return 1

    supervisor = Supervisor(
        specs=specs,
        runner=DefaultProcessRunner(),
    )

    # Register graceful signal handlers
    def _sig_handler(sig, frame):
        print("\nInterrupt received, shutting down gracefully...", file=sys.stderr)
        supervisor.request_stop()

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass  # Windows or non-main thread

    exit_code = supervisor.run()
    return exit_code
