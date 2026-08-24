from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any


class UnsupportedSchemaError(Exception):
    """Raised when the legacy database schema version is unsupported."""


@dataclass(frozen=True)
class EntityRecord:
    bounded_context: str
    entity_type: str
    opaque_id: str
    version: int
    digest: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def sort_key(self) -> tuple[str, int, str]:
        return (self.opaque_id, self.version, self.digest)


def compute_context_checksum(entities: list[EntityRecord]) -> str:
    """Compute SHA-256 checksum over sorted (opaque_id, version, digest) tuples."""
    sorted_tuples = sorted(e.sort_key() for e in entities)
    payload = json.dumps(sorted_tuples, sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ContextInventory:
    bounded_context: str
    entities: list[EntityRecord]
    count: int
    checksum: str


@dataclass(frozen=True)
class SourceInventory:
    source_uri: str
    source_fingerprint: str
    schema_version: int
    contexts: dict[str, ContextInventory]

    @property
    def total_count(self) -> int:
        return sum(ctx.count for ctx in self.contexts.values())

    @property
    def overall_checksum(self) -> str:
        all_entities: list[EntityRecord] = []
        for ctx in self.contexts.values():
            all_entities.extend(ctx.entities)
        return compute_context_checksum(all_entities)


def build_context_inventory(bounded_context: str, entities: list[EntityRecord]) -> ContextInventory:
    checksum = compute_context_checksum(entities)
    return ContextInventory(
        bounded_context=bounded_context,
        entities=entities,
        count=len(entities),
        checksum=checksum,
    )


def inventory_legacy_sqlite(db_path: str, expected_schema_version: int = 1) -> SourceInventory:
    """Read-only inventory of a legacy SQLite database using URI mode=ro."""
    source_fingerprint = "sha256:" + hashlib.sha256(db_path.encode()).hexdigest()
    uri = f"file:{db_path}?mode=ro"

    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row

    try:
        cur = conn.cursor()
        # Verify schema version if schema_version table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
        if cur.fetchone():
            cur.execute("SELECT version FROM schema_version LIMIT 1")
            row = cur.fetchone()
            if row and row["version"] != expected_schema_version:
                raise UnsupportedSchemaError(
                    f"Unsupported legacy schema version {row['version']} (expected {expected_schema_version})"
                )

        contexts: dict[str, list[EntityRecord]] = {
            "product_intelligence": [],
            "video_factory": [],
        }

        # Query legacy product/research entities if table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='legacy_products'")
        if cur.fetchone():
            cur.execute("SELECT id, name, version, payload_digest FROM legacy_products")
            for row in cur.fetchall():
                contexts["product_intelligence"].append(
                    EntityRecord(
                        bounded_context="product_intelligence",
                        entity_type="product",
                        opaque_id=str(row["id"]),
                        version=int(row["version"]),
                        digest=str(row["payload_digest"]),
                        metadata={"name": row["name"]},
                    )
                )

        # Query legacy video entities if table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='legacy_videos'")
        if cur.fetchone():
            cur.execute("SELECT id, title, version, video_digest FROM legacy_videos")
            for row in cur.fetchall():
                contexts["video_factory"].append(
                    EntityRecord(
                        bounded_context="video_factory",
                        entity_type="video",
                        opaque_id=str(row["id"]),
                        version=int(row["version"]),
                        digest=str(row["video_digest"]),
                        metadata={"title": row["title"]},
                    )
                )

        context_inventories = {
            ctx_name: build_context_inventory(ctx_name, entities)
            for ctx_name, entities in contexts.items()
        }

        return SourceInventory(
            source_uri=db_path,
            source_fingerprint=source_fingerprint,
            schema_version=expected_schema_version,
            contexts=context_inventories,
        )
    finally:
        conn.close()
