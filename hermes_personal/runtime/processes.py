from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from hermes_personal.observability.health import HealthStatus


class ProcessKind(Enum):
    GATEWAY_AGENT_RUNTIME = "gateway_agent_runtime"
    APPLICATION_API = "application_api"
    TELEGRAM_ADAPTER = "telegram_adapter"
    DURABLE_WORKERS = "durable_workers"
    MCP_HEALTH_DISCOVERY = "mcp_health_discovery"
    WEB_UI = "web_ui"


class WebMode(Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass(frozen=True, slots=True)
class ProcessSpec:
    kind: ProcessKind
    name: str
    command: tuple[str, ...]
    env_keys: tuple[str, ...]
    required: bool = True
    health_endpoint: str | None = None
    depends_on: tuple[ProcessKind, ...] = field(default_factory=tuple)
    web_mode: WebMode | None = None
    static_bundle_path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(self.command))
        object.__setattr__(self, "env_keys", tuple(self.env_keys))
        object.__setattr__(self, "depends_on", tuple(self.depends_on))

    def argv_contains_secret(self) -> bool:
        secret_indicators = (
            "password",
            "secret",
            "token",
            "key",
            "credential",
            "api_key",
            "apikey",
            "authorization",
            "bearer",
            "cookie",
            "private_key",
        )
        for arg in self.command:
            arg_lower = arg.lower()
            for indicator in secret_indicators:
                if indicator in arg_lower and not arg.startswith("${") and not arg.startswith("$"):
                    return True
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "name": self.name,
            "command": list(self.command),
            "env_keys": list(self.env_keys),
            "required": self.required,
            "health_endpoint": self.health_endpoint,
            "depends_on": [k.value for k in self.depends_on],
            "web_mode": self.web_mode.value if self.web_mode else None,
            "static_bundle_path": self.static_bundle_path,
        }


GATEWAY_AGENT_RUNTIME = ProcessSpec(
    kind=ProcessKind.GATEWAY_AGENT_RUNTIME,
    name="Gateway/Agent Runtime",
    command=(
        "python",
        "-m",
        "hermes_personal.orchestration.upstream_agent",
        "--config",
        "${HERMES_CONFIG}",
    ),
    env_keys=(
        "HERMES_CONFIG",
        "HERMES_HOME",
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
    ),
    required=True,
    health_endpoint="/health",
    depends_on=(),
)

APPLICATION_API = ProcessSpec(
    kind=ProcessKind.APPLICATION_API,
    name="Application API",
    command=(
        "python",
        "-m",
        "hermes_personal.api.server",
        "--config",
        "${HERMES_CONFIG}",
    ),
    env_keys=(
        "HERMES_CONFIG",
        "HERMES_HOME",
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ),
    required=True,
    health_endpoint="/health",
    depends_on=(ProcessKind.GATEWAY_AGENT_RUNTIME,),
)

TELEGRAM_ADAPTER = ProcessSpec(
    kind=ProcessKind.TELEGRAM_ADAPTER,
    name="Telegram Adapter",
    command=(
        "python",
        "-m",
        "hermes_personal.gateway.telegram",
        "--config",
        "${HERMES_CONFIG}",
    ),
    env_keys=(
        "HERMES_CONFIG",
        "HERMES_HOME",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
    ),
    required=True,
    health_endpoint="/health",
    depends_on=(ProcessKind.GATEWAY_AGENT_RUNTIME,),
)

DURABLE_WORKERS = ProcessSpec(
    kind=ProcessKind.DURABLE_WORKERS,
    name="Durable Workers",
    command=(
        "python",
        "-m",
        "hermes_personal.workflows.engine",
        "--config",
        "${HERMES_CONFIG}",
        "--worker",
    ),
    env_keys=(
        "HERMES_CONFIG",
        "HERMES_HOME",
        "DATABASE_URL",
    ),
    required=True,
    health_endpoint="/health",
    depends_on=(ProcessKind.GATEWAY_AGENT_RUNTIME,),
)

MCP_HEALTH_DISCOVERY = ProcessSpec(
    kind=ProcessKind.MCP_HEALTH_DISCOVERY,
    name="MCP Health/Discovery",
    command=(
        "python",
        "-m",
        "hermes_personal.capabilities.mcp_health",
        "--config",
        "${HERMES_CONFIG}",
    ),
    env_keys=(
        "HERMES_CONFIG",
        "HERMES_HOME",
        "MCP_REGISTRY_URL",
    ),
    required=True,
    health_endpoint="/health",
    depends_on=(ProcessKind.GATEWAY_AGENT_RUNTIME,),
)

WEB_UI_DEVELOPMENT = ProcessSpec(
    kind=ProcessKind.WEB_UI,
    name="Web UI (Development)",
    command=(
        "npm",
        "run",
        "dev",
        "--prefix",
        "${WEB_UI_PATH}",
    ),
    env_keys=(
        "HERMES_CONFIG",
        "HERMES_HOME",
        "WEB_UI_PATH",
        "VITE_API_URL",
    ),
    required=False,
    health_endpoint=None,
    depends_on=(ProcessKind.APPLICATION_API,),
    web_mode=WebMode.DEVELOPMENT,
)

WEB_UI_PRODUCTION = ProcessSpec(
    kind=ProcessKind.WEB_UI,
    name="Web UI (Production)",
    command=(),
    env_keys=(
        "HERMES_CONFIG",
        "HERMES_HOME",
        "WEB_UI_BUNDLE_PATH",
    ),
    required=False,
    health_endpoint=None,
    depends_on=(ProcessKind.APPLICATION_API,),
    web_mode=WebMode.PRODUCTION,
    static_bundle_path="${WEB_UI_BUNDLE_PATH}",
)

ALL_PROCESSES: tuple[ProcessSpec, ...] = (
    GATEWAY_AGENT_RUNTIME,
    APPLICATION_API,
    TELEGRAM_ADAPTER,
    DURABLE_WORKERS,
    MCP_HEALTH_DISCOVERY,
    WEB_UI_DEVELOPMENT,
    WEB_UI_PRODUCTION,
)

_PROCESS_MAP: dict[ProcessKind, ProcessSpec] = {p.kind: p for p in ALL_PROCESSES}


def get_process_spec(kind: ProcessKind) -> ProcessSpec:
    if kind not in _PROCESS_MAP:
        raise KeyError(f"Unknown process kind: {kind}")
    return _PROCESS_MAP[kind]


def assert_no_secrets_in_argv() -> None:
    violations: list[str] = []
    for spec in ALL_PROCESSES:
        if spec.argv_contains_secret():
            violations.append(f"{spec.name}: argv contains potential secret: {spec.command}")
    if violations:
        raise ValueError("Secret values detected in process argv:\n" + "\n".join(violations))


def get_web_ui_spec(mode: WebMode) -> ProcessSpec:
    if mode == WebMode.DEVELOPMENT:
        return WEB_UI_DEVELOPMENT
    return WEB_UI_PRODUCTION