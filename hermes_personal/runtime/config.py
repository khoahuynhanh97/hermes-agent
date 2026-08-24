from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

RuntimeMode = Literal["development", "production", "test"]


class RuntimeConfigError(Exception):
    """Raised when runtime configuration is invalid."""


@dataclass(frozen=True)
class RuntimeConfig:
    """Configuration contract for the hermes start runtime."""

    mode: RuntimeMode = "development"
    repo_root: Path = field(default_factory=lambda: Path.cwd())
    gateway_port: int = 8642
    app_api_port: int = 8000
    web_port: int = 3000
    python_executable: str = field(default_factory=lambda: sys.executable)
    node_executable: str = "npm"
    web_static_dir: Path | None = None
    web_static_digest: str = ""
    enable_telegram: bool = True
    enable_web: bool = True
    enable_workers: bool = True
    enable_mcp: bool = True
    secrets_env_keys: tuple[str, ...] = ("HERMES_TELEGRAM_TOKEN", "HERMES_API_KEY")

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        ports = [self.gateway_port, self.app_api_port]
        if self.mode == "development" and self.enable_web:
            ports.append(self.web_port)

        if len(ports) != len(set(ports)):
            raise RuntimeConfigError(f"Runtime ports must be unique: {ports}")

        if self.mode == "production" and self.enable_web:
            if self.web_static_dir is None:
                raise RuntimeConfigError("Production mode requires web_static_dir to be specified for Web surface")
