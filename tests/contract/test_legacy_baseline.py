import os
from pathlib import Path
import pytest


def test_legacy_configuration_declares_a_sqlite_target(tmp_path, monkeypatch):
    """Test that HERMES_DB_PATH environment variable controls SQLite database location."""
    monkeypatch.setenv("HERMES_DB_PATH", str(tmp_path / "hermes.db"))
    from hermes.config import load_settings
    assert load_settings().database_path == tmp_path / "hermes.db"