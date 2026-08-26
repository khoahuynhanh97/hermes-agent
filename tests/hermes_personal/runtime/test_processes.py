from __future__ import annotations

import os
from pathlib import Path
import pytest

from hermes_personal.runtime.config import RuntimeConfig, RuntimeConfigError, ProcessTopologyError
from hermes_personal.runtime.processes import (
    ProcessSpec,
    ProbeSpec,
    RestartPolicy,
    build_process_topology,
)


@pytest.fixture
def repo_root(tmp_path):
    root = tmp_path / "hermes_root"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_development_topology_contains_all_specs(repo_root):
    config = RuntimeConfig(
        mode="development",
        repo_root=repo_root,
        gateway_port=8642,
        app_api_port=8000,
        web_port=3000,
    )
    specs = build_process_topology(config)
    names = [s.name for s in specs]

    assert "gateway" in names
    assert "app_api" in names
    assert "mcp_discovery" in names
    assert "durable_worker" in names
    assert "telegram" in names
    assert "web_ui" in names
    web = next(spec for spec in specs if spec.name == "web_ui")
    assert "HERMES_DASHBOARD_URL" in web.env_keys
    assert "VITE_API_URL" not in web.env_keys
    assert web.argv[-4:] == ("--host", "127.0.0.1", "--port", "3000")
    assert web.argv[0] == ("npm.cmd" if os.name == "nt" else "npm")


def test_production_topology_serves_web_from_app_api(repo_root):
    dist_dir = repo_root / "web" / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    config = RuntimeConfig(
        mode="production",
        repo_root=repo_root,
        gateway_port=8642,
        app_api_port=8000,
        web_static_dir=dist_dir,
        web_static_digest="sha256:" + "a" * 64,
    )
    specs = build_process_topology(config)
    names = [s.name for s in specs]

    # In production, web_ui is NOT a separate dev server process
    assert "web_ui" not in names
    # app_api is present and references static dir
    assert "app_api" in names


def test_no_secret_values_in_argv(repo_root):
    config = RuntimeConfig(
        mode="development",
        repo_root=repo_root,
        secrets_env_keys=("HERMES_TELEGRAM_TOKEN", "HERMES_API_KEY"),
    )
    specs = build_process_topology(config)

    secret_markers = ("bot123456:ABC-DEF", "sk-live-12345", "supersecret", "ghp_123")
    for spec in specs:
        for arg in spec.argv:
            assert not any(marker in arg for marker in secret_markers), f"Secret leaked in argv of {spec.name}: {arg}"
        assert isinstance(spec.env_keys, tuple)


def test_specs_and_policies_are_immutable(repo_root):
    config = RuntimeConfig(mode="development", repo_root=repo_root)
    specs = build_process_topology(config)
    spec = specs[0]

    with pytest.raises(Exception):
        spec.name = "new_name"  # frozen dataclass

    with pytest.raises(Exception):
        spec.restart.max_attempts = 99  # frozen dataclass


def test_duplicate_ports_raise_validation_error(repo_root):
    with pytest.raises(RuntimeConfigError, match="unique"):
        RuntimeConfig(
            mode="development",
            repo_root=repo_root,
            gateway_port=8000,
            app_api_port=8000,  # collision
        )


def test_production_mode_requires_static_dir_and_digest(repo_root):
    with pytest.raises(RuntimeConfigError, match="web_static_dir"):
        config = RuntimeConfig(
            mode="production",
            repo_root=repo_root,
            web_static_dir=None,
        )

    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(RuntimeConfigError, match="web_static_digest"):
        RuntimeConfig(
            mode="production",
            repo_root=repo_root,
            web_static_dir=dist_dir,
            web_static_digest="",
        )


def test_validate_secrets_presence_without_logging_values(repo_root):
    config = RuntimeConfig(
        mode="development",
        repo_root=repo_root,
        secrets_env_keys=("HERMES_TELEGRAM_TOKEN", "HERMES_API_KEY"),
    )
    # Valid environment
    config.validate_secrets_presence({
        "HERMES_TELEGRAM_TOKEN": "secret_token_val",
        "HERMES_API_KEY": "secret_key_val",
    })

    # Missing secrets environment raises error with key names only, never values
    with pytest.raises(RuntimeConfigError, match="Missing required environment secrets: HERMES_API_KEY"):
        config.validate_secrets_presence({
            "HERMES_TELEGRAM_TOKEN": "secret_token_val",
            "HERMES_API_KEY": "",
        })


def test_disabled_telegram_does_not_require_telegram_secret(repo_root):
    config = RuntimeConfig(
        mode="development",
        repo_root=repo_root,
        enable_telegram=False,
    )

    config.validate_secrets_presence({"HERMES_API_KEY": "local-runtime-key"})


def test_fake_provider_is_explicit_and_development_only(repo_root):
    config = RuntimeConfig(
        mode="development",
        repo_root=repo_root,
        provider_mode="fake",
        enable_telegram=False,
        enable_mcp=False,
        enable_workers=False,
        enable_web=False,
    )

    gateway = next(spec for spec in build_process_topology(config) if spec.name == "gateway")
    assert gateway.argv[-2:] == ("--provider-mode", "fake")

    with pytest.raises(RuntimeConfigError, match="fake provider"):
        RuntimeConfig(
            mode="production",
            repo_root=repo_root,
            provider_mode="fake",
            web_static_dir=repo_root,
            web_static_digest="sha256:" + "0" * 64,
        )


def test_provider_mode_loads_from_runtime_config(tmp_path, repo_root):
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        """
runtime:
  provider_mode: fake
  enable_telegram: false
  enable_mcp: false
  enable_workers: false
  enable_web: false
""",
        encoding="utf-8",
    )

    config = RuntimeConfig.from_file(config_path, repo_root=repo_root)

    assert config.provider_mode == "fake"
    assert config.enable_telegram is False
