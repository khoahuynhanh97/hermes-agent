from __future__ import annotations

from pathlib import Path
import pytest

from hermes_personal.runtime.config import RuntimeConfig, RuntimeConfigError
from hermes_personal.runtime.processes import (
    ProcessSpec,
    ProbeSpec,
    RestartPolicy,
    build_process_topology,
    ProcessTopologyError,
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
        web_static_digest="sha256:fedcba9876543210",
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

    secret_markers = ("bot123456:ABC-DEF", "sk-live-12345", "password", "supersecret")
    for spec in specs:
        for arg in spec.argv:
            assert not any(marker in arg for marker in secret_markers), f"Secret leaked in argv of {spec.name}: {arg}"
        # Secret names must be in env_keys, not raw values
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


def test_production_mode_requires_static_dir_or_digest(repo_root):
    with pytest.raises(RuntimeConfigError, match="static"):
        config = RuntimeConfig(
            mode="production",
            repo_root=repo_root,
            web_static_dir=None,
        )
        build_process_topology(config)
