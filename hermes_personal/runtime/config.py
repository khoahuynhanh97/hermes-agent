from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from utils import fast_safe_load

RuntimeMode = Literal["development", "production", "test"]


class RuntimeConfigError(Exception):
    """Raised when runtime configuration is invalid."""


class ProcessTopologyError(Exception):
    """Raised when process topology specification is invalid."""


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
            if not self.web_static_digest:
                raise RuntimeConfigError("Production mode requires web_static_digest for static bundle verification")

    def validate_secrets_presence(self, env: dict[str, str] | None = None) -> None:
        """Check required secrets are present in environment without leaking their values in logs/errors."""
        active_env = os.environ if env is None else env
        missing: list[str] = []
        for key in self.secrets_env_keys:
            if not active_env.get(key):
                missing.append(key)
        if missing:
            raise RuntimeConfigError(f"Missing required environment secrets: {', '.join(missing)}")

    @classmethod
    def from_file(
        cls,
        config_path: Path | str,
        mode: RuntimeMode | None = None,
        repo_root: Path | None = None,
    ) -> RuntimeConfig:
        """Load runtime configuration from YAML config file."""
        p = Path(config_path)
        if not p.is_file():
            raise RuntimeConfigError(f"Config file not found: {p}")

        try:
            content = p.read_text(encoding="utf-8")
            data = fast_safe_load(content) or {}
        except Exception as ex:
            raise RuntimeConfigError(f"Failed to read config file {p}: {ex}") from ex

        if not isinstance(data, dict):
            raise RuntimeConfigError(f"Invalid YAML config root in {p}: expected dictionary")

        runtime_data: dict[str, Any] = data.get("runtime", {})
        if not isinstance(runtime_data, dict):
            runtime_data = {}

        kwargs: dict[str, Any] = {}
        if mode is not None:
            kwargs["mode"] = mode
        elif "mode" in runtime_data:
            kwargs["mode"] = runtime_data["mode"]

        if repo_root is not None:
            kwargs["repo_root"] = repo_root

        for key in (
            "gateway_port",
            "app_api_port",
            "web_port",
            "python_executable",
            "node_executable",
            "enable_telegram",
            "enable_web",
            "enable_workers",
            "enable_mcp",
            "web_static_digest",
        ):
            if key in runtime_data:
                kwargs[key] = runtime_data[key]

        if "web_static_dir" in runtime_data and runtime_data["web_static_dir"]:
            kwargs["web_static_dir"] = Path(runtime_data["web_static_dir"])

        return cls(**kwargs)