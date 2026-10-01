from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field
from enum import Enum

from .inventory import EntityRecord, SourceInventory, ContextInventory, compute_context_checksum


class ReconciliationStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH_COUNT = "MISMATCH_COUNT"
    MISMATCH_CHECKSUM = "MISMATCH_CHECKSUM"
    MISSING_TARGET_ROW = "MISSING_TARGET_ROW"
    DUPLICATE_SOURCE_IDENTITY = "DUPLICATE_SOURCE_IDENTITY"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"


@dataclass(frozen=True)
class ReconciliationResult:
    status: ReconciliationStatus
    source_count: int
    target_count: int
    source_checksum: str
    target_checksum: str
    discrepancies: list[str] = field(default_factory=list)

    @property
    def is_match(self) -> bool:
        return self.status == ReconciliationStatus.MATCH


@dataclass(frozen=True)
class MigrationManifest:
    manifest_id: str
    source_uri_fingerprint: str
    source_schema_version: int
    target_ids_created: list[str]
    started_at: str
    completed_at: str
    status: str
    rollback_instructions: list[str] = field(default_factory=list)


def reconcile_inventories(source: SourceInventory, target: SourceInventory) -> ReconciliationResult:
    """Reconcile source and target inventories by entity count and checksum over sorted tuples."""
    discrepancies: list[str] = []

    # Check for duplicate identities in source
    source_identities: set[tuple[str, str]] = set()
    for ctx in source.contexts.values():
        for entity in ctx.entities:
            key = (entity.bounded_context, entity.opaque_id)
            if key in source_identities:
                discrepancies.append(f"Duplicate source entity identity: context={entity.bounded_context}, id={entity.opaque_id}")
                return ReconciliationResult(
                    status=ReconciliationStatus.DUPLICATE_SOURCE_IDENTITY,
                    source_count=source.total_count,
                    target_count=target.total_count,
                    source_checksum=source.overall_checksum,
                    target_checksum=target.overall_checksum,
                    discrepancies=discrepancies,
                )
            source_identities.add(key)

    # Check missing target rows
    target_entity_map: dict[tuple[str, str], EntityRecord] = {}
    for ctx in target.contexts.values():
        for entity in ctx.entities:
            target_entity_map[(entity.bounded_context, entity.opaque_id)] = entity

    for ctx in source.contexts.values():
        for s_ent in ctx.entities:
            key = (s_ent.bounded_context, s_ent.opaque_id)
            if key not in target_entity_map:
                discrepancies.append(f"Missing target record for source entity {key}")
            else:
                t_ent = target_entity_map[key]
                if s_ent.digest != t_ent.digest or s_ent.version != t_ent.version:
                    discrepancies.append(
                        f"Digest/version mismatch for entity {key}: source=(v={s_ent.version}, d={s_ent.digest}) vs target=(v={t_ent.version}, d={t_ent.digest})"
                    )

    source_cnt = source.total_count
    target_cnt = target.total_count
    source_chk = source.overall_checksum
    target_chk = target.overall_checksum

    if discrepancies:
        if any("Missing target record" in d for d in discrepancies):
            status = ReconciliationStatus.MISSING_TARGET_ROW
        else:
            status = ReconciliationStatus.MISMATCH_CHECKSUM
        return ReconciliationResult(
            status=status,
            source_count=source_cnt,
            target_count=target_cnt,
            source_checksum=source_chk,
            target_checksum=target_chk,
            discrepancies=discrepancies,
        )

    if source_cnt != target_cnt:
        return ReconciliationResult(
            status=ReconciliationStatus.MISMATCH_COUNT,
            source_count=source_cnt,
            target_count=target_cnt,
            source_checksum=source_chk,
            target_checksum=target_chk,
            discrepancies=[f"Count mismatch: source {source_cnt} vs target {target_cnt}"],
        )

    if source_chk != target_chk:
        return ReconciliationResult(
            status=ReconciliationStatus.MISMATCH_CHECKSUM,
            source_count=source_cnt,
            target_count=target_cnt,
            source_checksum=source_chk,
            target_checksum=target_chk,
            discrepancies=["Overall checksum mismatch between source and target"],
        )

    return ReconciliationResult(
        status=ReconciliationStatus.MATCH,
        source_count=source_cnt,
        target_count=target_cnt,
        source_checksum=source_chk,
        target_checksum=target_chk,
        discrepancies=[],
    )


class TargetStoreAdapter:
    """In-memory or SQLite-backed target store for migrated records."""

    def __init__(self) -> None:
        self.records: dict[str, EntityRecord] = {}

    def insert(self, entity: EntityRecord) -> None:
        key = f"{entity.bounded_context}:{entity.opaque_id}"
        self.records[key] = entity

    def exists(self, bounded_context: str, opaque_id: str) -> bool:
        key = f"{bounded_context}:{opaque_id}"
        return key in self.records

    def delete(self, target_id: str) -> bool:
        """Target-only record deletion by target composite key."""
        if target_id in self.records:
            del self.records[target_id]
            return True
        return False

    def export_inventory(self) -> SourceInventory:
        contexts: dict[str, list[EntityRecord]] = {}
        for entity in self.records.values():
            contexts.setdefault(entity.bounded_context, []).append(entity)

        context_inventories = {
            ctx_name: ContextInventory(
                bounded_context=ctx_name,
                entities=entities,
                count=len(entities),
                checksum=compute_context_checksum(entities),
            )
            for ctx_name, entities in contexts.items()
        }

        return SourceInventory(
            source_uri="memory://target_store",
            source_fingerprint="sha256:target_store_fingerprint",
            schema_version=1,
            contexts=context_inventories,
        )


def migrate_legacy_data(source_inventory: SourceInventory, target_store: TargetStoreAdapter) -> MigrationManifest:
    """Execute idempotent migration of legacy source inventory to target store without modifying source."""
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest_id = f"mig_{hashlib.sha256(f'{source_inventory.source_fingerprint}:{started_at}'.encode()).hexdigest()[:12]}"
    target_ids_created: list[str] = []

    for ctx in source_inventory.contexts.values():
        for entity in ctx.entities:
            target_key = f"{entity.bounded_context}:{entity.opaque_id}"
            if not target_store.exists(entity.bounded_context, entity.opaque_id):
                target_store.insert(entity)
                target_ids_created.append(target_key)

    completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rollback_instructions = [
        f"DELETE FROM target_entities WHERE target_id IN ({', '.join(target_ids_created)})",
        "NEVER delete, modify, or truncate source database or legacy media directories.",
    ]

    return MigrationManifest(
        manifest_id=manifest_id,
        source_uri_fingerprint=source_inventory.source_fingerprint,
        source_schema_version=source_inventory.schema_version,
        target_ids_created=target_ids_created,
        started_at=started_at,
        completed_at=completed_at,
        status="COMPLETED",
        rollback_instructions=rollback_instructions,
    )


def rollback_migration(manifest: MigrationManifest, target_store: TargetStoreAdapter) -> int:
    """Roll back migration by removing ONLY target records created in the manifest.

    Guarantees zero modifications or deletions to legacy source stores or media files.
    """
    removed_count = 0
    for target_id in manifest.target_ids_created:
        if target_store.delete(target_id):
            removed_count += 1
    return removed_count
