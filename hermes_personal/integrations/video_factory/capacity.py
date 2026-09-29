"""Shared SQLite admission for Product Video paid provider operations."""

from __future__ import annotations

import sqlite3
import time
import os
import uuid
from typing import Any


_PROCESS_LEASE_TOKEN = uuid.uuid4().hex


def process_lease_owner() -> str:
    """Keep ownership stable across runtime instances in one worker process."""
    return f"{os.getpid()}:{_PROCESS_LEASE_TOKEN}"


def configured_capacity(provider_kind: str) -> int:
    """Read a bounded behavioral setting; the safe default is one operation."""
    from hermes_cli.config import load_config

    config = load_config()
    video = config.get("video_factory", {}) if isinstance(config, dict) else {}
    capacity = video.get("provider_capacity", {}) if isinstance(video, dict) else {}
    raw = capacity.get(provider_kind, 1) if isinstance(capacity, dict) else 1
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError(f"video_factory.provider_capacity.{provider_kind} must be a positive integer")
    return raw


class ProviderCapacityStore:
    DDL = """
    CREATE TABLE IF NOT EXISTS video_factory_provider_capacity (
        provider_kind TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        profile_id TEXT NOT NULL DEFAULT '',
        lease_owner TEXT NOT NULL,
        lease_expires_at REAL NOT NULL,
        provider_operation_id TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(provider_kind, operation_id)
    );
    CREATE INDEX IF NOT EXISTS idx_vf_capacity_provider
    ON video_factory_provider_capacity(provider_kind, profile_id);
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(self.DDL)

    def try_acquire(
        self,
        *,
        provider_kind: str,
        operation_id: str,
        lease_owner: str,
        limit: int,
        profile_id: str = "",
        lease_seconds: float = 300.0,
        reconciled_takeover: bool = False,
        reconciliation_only: bool = False,
    ) -> bool:
        if not provider_kind or not operation_id or not lease_owner:
            raise ValueError("provider, operation and lease owner are required")
        if isinstance(limit, bool) or limit < 1 or lease_seconds <= 0:
            raise ValueError("provider capacity and lease duration must be positive")
        now = time.time()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self.connection.execute(
                "SELECT * FROM video_factory_provider_capacity WHERE provider_kind=? AND operation_id=?",
                (provider_kind, operation_id),
            ).fetchone()
            if existing:
                if existing["profile_id"] != profile_id:
                    raise ValueError("provider capacity profile binding conflict")
                if existing["lease_owner"] == lease_owner:
                    self.connection.execute(
                        "UPDATE video_factory_provider_capacity SET lease_expires_at=? WHERE provider_kind=? AND operation_id=?",
                        (now + lease_seconds, provider_kind, operation_id),
                    )
                    self.connection.commit()
                    return True
                if existing["lease_expires_at"] > now or not (
                    reconciliation_only
                    or (reconciled_takeover and existing["provider_operation_id"])
                ):
                    self.connection.commit()
                    return False
                self.connection.execute(
                    "UPDATE video_factory_provider_capacity SET lease_owner=?, lease_expires_at=? WHERE provider_kind=? AND operation_id=?",
                    (lease_owner, now + lease_seconds, provider_kind, operation_id),
                )
                self.connection.commit()
                return True
            count = self.connection.execute(
                "SELECT COUNT(*) FROM video_factory_provider_capacity WHERE provider_kind=?",
                (provider_kind,),
            ).fetchone()[0]
            if count >= limit:
                self.connection.commit()
                return False
            if profile_id and self.connection.execute(
                "SELECT 1 FROM video_factory_provider_capacity WHERE profile_id=? LIMIT 1",
                (profile_id,),
            ).fetchone():
                self.connection.commit()
                return False
            self.connection.execute(
                "INSERT INTO video_factory_provider_capacity VALUES (?, ?, ?, ?, ?, '')",
                (provider_kind, operation_id, profile_id, lease_owner, now + lease_seconds),
            )
            self.connection.commit()
            return True
        except Exception:
            self.connection.rollback()
            raise

    def bind_provider_operation(self, provider_kind: str, operation_id: str, provider_operation_id: str) -> None:
        if not provider_operation_id:
            raise ValueError("provider operation ID is required")
        with self.connection:
            row = self.connection.execute(
                "SELECT provider_operation_id FROM video_factory_provider_capacity WHERE provider_kind=? AND operation_id=?",
                (provider_kind, operation_id),
            ).fetchone()
            if row is None or row["provider_operation_id"] not in {"", provider_operation_id}:
                raise ValueError("provider capacity operation binding conflict")
            self.connection.execute(
                "UPDATE video_factory_provider_capacity SET provider_operation_id=? WHERE provider_kind=? AND operation_id=?",
                (provider_operation_id, provider_kind, operation_id),
            )

    def release_terminal(self, provider_kind: str, operation_id: str) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM video_factory_provider_capacity WHERE provider_kind=? AND operation_id=?",
                (provider_kind, operation_id),
            )

    def active(self, provider_kind: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM video_factory_provider_capacity WHERE provider_kind=?",
            (provider_kind,),
        )]
