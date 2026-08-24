from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from hermes_cli.plugins import PluginManager
from hermes_personal.runtime.cli import handle_start, setup_start_parser
from hermes_personal.runtime.plugin import register as register_start_plugin
from hermes_personal.runtime.readiness import StartupReport, StartupStepRecord, StartupStepStatus


def test_setup_start_parser_defines_exact_flags():
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


def test_plugin_discovery_discovers_start_command(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - hermes-personal\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))

    manager = PluginManager()
    manager.discover_and_load()
    assert "start" in manager._cli_commands
    cmd = manager._cli_commands["start"]
    assert cmd["name"] == "start"
    assert cmd["setup_fn"] is setup_start_parser
    assert cmd["handler_fn"] is handle_start


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
