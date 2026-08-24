from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from hermes_cli.plugins import PluginManager
from hermes_personal.runtime.cli import handle_start, setup_start_parser
from hermes_personal.runtime.config import RuntimeConfig
from hermes_personal.runtime.plugin import register as register_start_plugin
from hermes_personal.runtime.readiness import StartupReport, StartupStepRecord, StartupStepStatus


def test_setup_start_parser_defines_exact_flags_and_choices():
    parser = argparse.ArgumentParser(prog="hermes")
    subparsers = parser.add_subparsers(dest="command")
    start_parser = subparsers.add_parser("start")
    setup_start_parser(start_parser)

    # Verify default parsing
    args = parser.parse_args(["start"])
    assert args.mode == "development"
    assert args.config is None
    assert args.no_open_browser is False

    # Verify explicit flags
    args2 = parser.parse_args(["start", "--mode", "production", "--config", "/etc/hermes.yaml", "--no-open-browser"])
    assert args2.mode == "production"
    assert args2.config == "/etc/hermes.yaml"
    assert args2.no_open_browser is True

    # Assert only expected flags exist
    mode_action = next(a for a in start_parser._actions if a.dest == "mode")
    assert mode_action.choices == ["development", "production"]

    actions = [a.dest for a in start_parser._actions if a.dest != "help"]
    assert set(actions) == {"mode", "config", "no_open_browser"}


def test_plugin_registration_registers_exact_start_command():
    mock_ctx = MagicMock()
    register_start_plugin(mock_ctx)

    mock_ctx.register_cli_command.assert_called_once()
    kwargs = mock_ctx.register_cli_command.call_args.kwargs
    assert kwargs["name"] == "start"
    assert kwargs["setup_fn"] is setup_start_parser
    assert kwargs["handler_fn"] is handle_start


def test_public_plugin_discovery_and_deferred_loading_contract(tmp_path, monkeypatch):
    """Proves why bundled project plugin without plugins.enabled requires deferred/targeted loading."""
    home = tmp_path / "home"
    home.mkdir()
    # Empty config without plugins.enabled
    (home / "config.yaml").write_text("model: test-model\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))

    manager = PluginManager()
    manager.discover_and_load()
    # Standalone bundled plugin is discovered but disabled by default
    assert "hermes-personal" in manager._plugins
    assert manager._plugins["hermes-personal"].enabled is False

    # When resolved for start command, _load_plugin registers start
    manager._load_plugin(manager._plugins["hermes-personal"].manifest)
    assert "start" in manager._cli_commands
    cmd = manager._cli_commands["start"]
    assert cmd["name"] == "start"
    assert cmd["setup_fn"] is setup_start_parser
    assert cmd["handler_fn"] is handle_start


def test_handle_start_with_custom_config_file(tmp_path):
    custom_cfg = tmp_path / "custom_hermes.yaml"
    custom_cfg.write_text(
        """
runtime:
  mode: development
  gateway_port: 9000
  app_api_port: 9001
  web_port: 9002
""",
        encoding="utf-8",
    )

    with patch("hermes_personal.runtime.cli.StartupCoordinator") as mock_coord_cls, \
         patch("hermes_personal.runtime.cli.Supervisor") as mock_sup_cls:
        mock_coord = MagicMock()
        mock_coord.prepare.return_value = StartupReport(
            overall_status=StartupStepStatus.COMPLETED,
            steps=(),
            started_at=0.0,
            completed_at=0.01,
            total_latency_ms=10.0,
        )
        mock_coord_cls.return_value = mock_coord
        mock_sup = MagicMock()
        mock_sup.run.return_value = 0
        mock_sup_cls.return_value = mock_sup

        args = argparse.Namespace(mode="development", config=str(custom_cfg), no_open_browser=True)
        exit_code = handle_start(args)
        assert exit_code == 0

        # Verify StartupCoordinator was given config loaded from custom_cfg
        passed_config: RuntimeConfig = mock_coord_cls.call_args.kwargs["config"]
        assert passed_config.gateway_port == 9000
        assert passed_config.app_api_port == 9001
        assert passed_config.web_port == 9002


def test_handle_start_fails_on_missing_config_file(tmp_path, capsys):
    missing_cfg = tmp_path / "non_existent.yaml"
    args = argparse.Namespace(mode="development", config=str(missing_cfg), no_open_browser=True)
    exit_code = handle_start(args)

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Configuration validation error" in captured.err
    assert "Config file not found" in captured.err


@patch("hermes_personal.runtime.cli.StartupCoordinator")
def test_handle_start_fails_on_unready_startup(mock_coord_cls, capsys):
    mock_coord = MagicMock()
    failed_report = StartupReport(
        overall_status=StartupStepStatus.FAILED,
        steps=(
            StartupStepRecord(
                name="db_migration",
                status=StartupStepStatus.FAILED,
                start_time=0.0,
                end_time=0.1,
                latency_ms=100.0,
                error_code="DB_MIGRATION_FAILED",
                error_message="migration lock error (secret=sk-12345)",
            ),
        ),
        started_at=0.0,
        completed_at=0.1,
        total_latency_ms=100.0,
        failure_code="DB_MIGRATION_FAILED",
    )
    mock_coord.prepare.return_value = failed_report
    mock_coord_cls.return_value = mock_coord

    args = argparse.Namespace(mode="development", config=None, no_open_browser=True)
    exit_code = handle_start(args)

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Startup readiness failed at step 'db_migration' [DB_MIGRATION_FAILED]" in captured.err
    # Redaction verification: secret in error message must be masked
    assert "sk-12345" not in captured.err


@patch("hermes_personal.runtime.cli.Supervisor")
@patch("hermes_personal.runtime.cli.StartupCoordinator")
def test_handle_start_runs_supervisor_on_readiness(mock_coord_cls, mock_sup_cls, capsys):
    mock_coord = MagicMock()
    ready_report = StartupReport(
        overall_status=StartupStepStatus.COMPLETED,
        steps=(
            StartupStepRecord(
                name="ingress_ready",
                status=StartupStepStatus.COMPLETED,
                start_time=0.0,
                end_time=0.05,
                latency_ms=50.0,
            ),
        ),
        started_at=0.0,
        completed_at=0.05,
        total_latency_ms=50.0,
    )
    mock_coord.prepare.return_value = ready_report
    mock_coord_cls.return_value = mock_coord

    mock_sup = MagicMock()
    mock_sup.run.return_value = 0
    mock_sup_cls.return_value = mock_sup

    args = argparse.Namespace(mode="development", config=None, no_open_browser=True)
    exit_code = handle_start(args)

    assert exit_code == 0
    mock_sup.run.assert_called_once()
    captured = capsys.readouterr()
    assert "Hermes runtime ready (50.0ms)" in captured.out
