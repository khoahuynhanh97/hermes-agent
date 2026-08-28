from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hermes_personal.runtime.config import ProcessTopologyError, RuntimeConfig

ProbeType = Literal["http", "tcp", "exec", "file", "noop"]


@dataclass(frozen=True)
class ProbeSpec:
    """Readiness probe specification for a process."""

    probe_type: ProbeType
    endpoint: str = ""
    interval_seconds: float = 1.0
    timeout_seconds: float = 2.0
    initial_delay_seconds: float = 0.5


@dataclass(frozen=True)
class RestartPolicy:
    """Bounded exponential restart policy for a supervised process."""

    max_attempts: int = 5
    window_seconds: float = 60.0
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0


@dataclass(frozen=True)
class ProcessSpec:
    """Immutable specification for a supervised child process."""

    name: str
    argv: tuple[str, ...]
    cwd: Path
    env_keys: tuple[str, ...]
    required: bool
    readiness_probe: ProbeSpec
    shutdown_timeout_seconds: float = 5.0
    restart: RestartPolicy = field(default_factory=RestartPolicy)

    def argv_contains_secret(self) -> bool:
        secret_indicators = (
            "password",
            "secret",
            "token",
            "credential",
            "api_key",
            "apikey",
            "authorization",
            "bearer",
            "cookie",
            "private_key",
            "ghp_",
            "sk-",
        )
        for arg in self.argv:
            arg_lower = arg.lower()
            for indicator in secret_indicators:
                if indicator in arg_lower and not arg.startswith("--"):
                    return True
        return False


def build_process_topology(config: RuntimeConfig) -> tuple[ProcessSpec, ...]:
    """Generate ordered, immutable process specifications for the Hermes runtime."""
    config.validate()
    specs: list[ProcessSpec] = []
    py = config.python_executable
    root = config.repo_root

    # 1. Gateway / Agent Runtime
    specs.append(
        ProcessSpec(
            name="gateway",
            argv=(
                py,
                "-m",
                "hermes_personal.runtime.gateway_server",
                "--port",
                str(config.gateway_port),
                "--provider-mode",
                config.provider_mode,
            ),
            cwd=root,
            env_keys=(
                "HERMES_HOME",
                "HERMES_PORT",
                "HERMES_API_KEY",
                "HERMES_OWNER_ID",
                "HERMES_EXTERNAL_SUBJECT",
                "HERMES_INFERENCE_MODEL",
                "HERMES_INFERENCE_PROVIDER",
            ),
            required=True,
            readiness_probe=ProbeSpec(
                probe_type="http",
                endpoint=f"http://127.0.0.1:{config.gateway_port}/health/ready",
            ),
            shutdown_timeout_seconds=5.0,
            restart=RestartPolicy(max_attempts=5, window_seconds=60.0, base_backoff_seconds=1.0),
        )
    )

    # 2. Application API Server
    app_api_argv = [
        py,
        "-m",
        "hermes_personal.api.server",
        "--port",
        str(config.app_api_port),
        "--gateway-port",
        str(config.gateway_port),
    ]
    if config.mode == "production" and config.web_static_dir:
        app_api_argv.extend(["--static-dir", str(config.web_static_dir)])
        if config.web_static_digest:
            app_api_argv.extend(["--static-digest", config.web_static_digest])

    specs.append(
        ProcessSpec(
            name="app_api",
            argv=tuple(app_api_argv),
            cwd=root,
            env_keys=(
                "HERMES_HOME",
                "HERMES_API_PORT",
                "HERMES_API_KEY",
                "HERMES_OWNER_ID",
            ),
            required=True,
            readiness_probe=ProbeSpec(
                probe_type="http",
                endpoint=f"http://127.0.0.1:{config.app_api_port}/healthz",
            ),
            shutdown_timeout_seconds=5.0,
            restart=RestartPolicy(max_attempts=5, window_seconds=60.0, base_backoff_seconds=1.0),
        )
    )

    # 3. MCP Discovery & Health
    if config.enable_mcp:
        specs.append(
            ProcessSpec(
                name="mcp_discovery",
                argv=(
                    py,
                    "-m",
                    "hermes_personal.capabilities.mcp_runner",
                    "--action",
                    "discover",
                ),
                cwd=root,
                env_keys=("HERMES_HOME",),
                required=True,
                readiness_probe=ProbeSpec(probe_type="exec", endpoint="mcp_snapshot_check"),
                shutdown_timeout_seconds=3.0,
                restart=RestartPolicy(max_attempts=3, window_seconds=60.0, base_backoff_seconds=2.0),
            )
        )

    # 4. Durable Background Workers
    if config.enable_workers:
        specs.append(
            ProcessSpec(
                name="durable_worker",
                argv=(
                    py,
                    "-m",
                    "hermes_personal.workflows.worker",
                ),
                cwd=root,
                env_keys=("HERMES_HOME",),
                required=True,
                readiness_probe=ProbeSpec(probe_type="noop"),
                shutdown_timeout_seconds=10.0,
                restart=RestartPolicy(max_attempts=10, window_seconds=120.0, base_backoff_seconds=1.0),
            )
        )

    # 5. Telegram Platform Adapter
    if config.enable_telegram:
        specs.append(
            ProcessSpec(
                name="telegram",
                argv=(
                    py,
                    "-m",
                    "hermes_personal.gateway.platforms.telegram_runner",
                ),
                cwd=root,
                env_keys=("HERMES_HOME", "HERMES_TELEGRAM_TOKEN"),
                required=False,  # Optional adapter
                readiness_probe=ProbeSpec(probe_type="noop"),
                shutdown_timeout_seconds=5.0,
                restart=RestartPolicy(max_attempts=5, window_seconds=60.0, base_backoff_seconds=2.0),
            )
        )

    # 6. Web UI (Development frontend dev server)
    if config.enable_web and config.mode == "development":
        web_cwd = root / "web" if (root / "web").exists() else root
        specs.append(
            ProcessSpec(
                name="web_ui",
                argv=(
                    config.node_executable,
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(config.web_port),
                ),
                cwd=web_cwd,
                env_keys=("HERMES_DASHBOARD_URL", "PORT"),
                required=False,
                readiness_probe=ProbeSpec(
                    probe_type="http",
                    endpoint=f"http://127.0.0.1:{config.web_port}",
                ),
                shutdown_timeout_seconds=3.0,
                restart=RestartPolicy(max_attempts=3, window_seconds=60.0, base_backoff_seconds=2.0),
            )
        )

    # Safety validation: ensure no secret values leaked in argv
    for spec in specs:
        if spec.argv_contains_secret():
            raise ProcessTopologyError(f"Potential secret detected in argv of process '{spec.name}'")

    return tuple(specs)
