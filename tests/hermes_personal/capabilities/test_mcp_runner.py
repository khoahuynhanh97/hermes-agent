import json
import os
import subprocess
import sys

import pytest

from hermes_personal.capabilities import mcp_runner
from hermes_personal.capabilities.discovery import DEFAULT_WIRE_BINDING_RULES


def registry():
    return {
        rule.accepted_wire_names[0]: {
            "type": "function",
            "function": {"name": rule.accepted_wire_names[0], "parameters": {"type": "object"}},
        }
        for rule in DEFAULT_WIRE_BINDING_RULES
    }


def test_discovery_persists_snapshot_and_check_requires_matching_process(tmp_path):
    snapshot = mcp_runner.run_discovery(tmp_path, registry=registry(), pid=123)
    assert mcp_runner.check_snapshot(tmp_path, expected_pid=123)
    assert not mcp_runner.check_snapshot(tmp_path, expected_pid=456)
    marker = json.loads((tmp_path / "mcp-discovery-ready.json").read_text())
    assert marker["snapshot_id"] == snapshot.snapshot_id


def test_failed_discovery_invalidates_old_readiness(tmp_path):
    mcp_runner.run_discovery(tmp_path, registry=registry(), pid=123)
    with pytest.raises(Exception):
        mcp_runner.run_discovery(tmp_path, registry={}, pid=123)
    assert not mcp_runner.check_snapshot(tmp_path, expected_pid=123)


def test_check_missing_database_is_read_only(tmp_path):
    before = set(tmp_path.iterdir())
    assert not mcp_runner.check_snapshot(tmp_path, expected_pid=123)
    assert set(tmp_path.iterdir()) == before


def test_check_cli_exits_after_reading_real_sqlite_snapshot(tmp_path):
    mcp_runner.run_discovery(tmp_path, registry=registry(), pid=123)
    result = subprocess.run(
        [sys.executable, "-m", "hermes_personal.capabilities.mcp_runner",
         "--action", "check", "--expected-pid", "123"],
        env={**os.environ, "HERMES_HOME": str(tmp_path)},
        capture_output=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
