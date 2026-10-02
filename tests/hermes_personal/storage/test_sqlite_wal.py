"""Tests for SQLite WAL mode and concurrency settings."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from hermes_personal.storage.sqlite import connect


def test_connection_uses_wal_mode():
    """Verify that connections are configured with WAL journal mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = connect(db_path)
        try:
            result = conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0].upper() == "WAL"
        finally:
            conn.close()


def test_connection_has_busy_timeout():
    """Verify that connections have busy_timeout set to 10 seconds."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = connect(db_path)
        try:
            result = conn.execute("PRAGMA busy_timeout").fetchone()
            assert result[0] == 10000
        finally:
            conn.close()


def test_connection_has_synchronous_normal():
    """Verify that connections use synchronous=NORMAL for WAL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = connect(db_path)
        try:
            result = conn.execute("PRAGMA synchronous").fetchone()
            assert result[0] == 1
        finally:
            conn.close()


def test_foreign_keys_still_enabled():
    """Verify that foreign_keys pragma is still ON after WAL changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = connect(db_path)
        try:
            result = conn.execute("PRAGMA foreign_keys").fetchone()
            assert result[0] == 1
        finally:
            conn.close()
