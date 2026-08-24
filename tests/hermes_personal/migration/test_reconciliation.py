from __future__ import annotations

import sqlite3
import pytest

from hermes_personal.migration import (
    UnsupportedSchemaError,
    EntityRecord,
    ContextInventory,
    SourceInventory,
    ReconciliationStatus,
    TargetStoreAdapter,
    inventory_legacy_sqlite,
    reconcile_inventories,
    migrate_legacy_data,
    rollback_migration,
)


@pytest.fixture
def legacy_db(tmp_path):
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_file))
    with conn:
        conn.execute("CREATE TABLE schema_version (version INTEGER)")
        conn.execute("INSERT INTO schema_version VALUES (1)")
        conn.execute("CREATE TABLE legacy_products (id TEXT PRIMARY KEY, name TEXT, version INTEGER, payload_digest TEXT)")
        conn.execute("INSERT INTO legacy_products VALUES ('p1', 'Smart Watch', 1, 'sha256:product_digest_1')")
        conn.execute("INSERT INTO legacy_products VALUES ('p2', 'Fitness Tracker', 1, 'sha256:product_digest_2')")
        conn.execute("CREATE TABLE legacy_videos (id TEXT PRIMARY KEY, title TEXT, version INTEGER, video_digest TEXT)")
        conn.execute("INSERT INTO legacy_videos VALUES ('v1', 'Watch Promo', 1, 'sha256:video_digest_1')")
    conn.close()
    return str(db_file)


def test_identical_inventory_reconciliation(legacy_db):
    """Prove that migrating legacy data and reconciling results in 100% MATCH."""
    source_inv = inventory_legacy_sqlite(legacy_db)
    assert source_inv.total_count == 3

    target_store = TargetStoreAdapter()
    manifest = migrate_legacy_data(source_inv, target_store)
    assert manifest.status == "COMPLETED"
    assert len(manifest.target_ids_created) == 3

    target_inv = target_store.export_inventory()
    result = reconcile_inventories(source_inv, target_inv)
    assert result.is_match is True
    assert result.status == ReconciliationStatus.MATCH
    assert result.source_count == 3
    assert result.target_count == 3
    assert result.source_checksum == result.target_checksum


def test_missing_target_row_detection(legacy_db):
    """Prove that missing rows in the target store are flagged as MISSING_TARGET_ROW."""
    source_inv = inventory_legacy_sqlite(legacy_db)
    target_store = TargetStoreAdapter()
    migrate_legacy_data(source_inv, target_store)

    # Delete one entity from target
    target_store.delete("product_intelligence:p1")

    target_inv = target_store.export_inventory()
    result = reconcile_inventories(source_inv, target_inv)
    assert result.is_match is False
    assert result.status == ReconciliationStatus.MISSING_TARGET_ROW
    assert any("Missing target record" in d for d in result.discrepancies)


def test_digest_mismatch_detection(legacy_db):
    """Prove that altered digests or versions in the target store trigger MISMATCH_CHECKSUM."""
    source_inv = inventory_legacy_sqlite(legacy_db)
    target_store = TargetStoreAdapter()
    migrate_legacy_data(source_inv, target_store)

    # Corrupt a record in target
    target_store.insert(
        EntityRecord(
            bounded_context="product_intelligence",
            entity_type="product",
            opaque_id="p1",
            version=1,
            digest="sha256:corrupted_digest",
        )
    )

    target_inv = target_store.export_inventory()
    result = reconcile_inventories(source_inv, target_inv)
    assert result.is_match is False
    assert result.status == ReconciliationStatus.MISMATCH_CHECKSUM
    assert any("Digest/version mismatch" in d for d in result.discrepancies)


def test_duplicate_source_identity_detection():
    """Prove that duplicate identities in source are flagged as DUPLICATE_SOURCE_IDENTITY."""
    e1 = EntityRecord(bounded_context="product_intelligence", entity_type="product", opaque_id="p1", version=1, digest="sha256:d1")
    e2 = EntityRecord(bounded_context="product_intelligence", entity_type="product", opaque_id="p1", version=2, digest="sha256:d2")

    source_ctx = ContextInventory(
        bounded_context="product_intelligence",
        entities=[e1, e2],
        count=2,
        checksum="sha256:chk",
    )
    source_inv = SourceInventory(
        source_uri="memory://dup",
        source_fingerprint="sha256:dup",
        schema_version=1,
        contexts={"product_intelligence": source_ctx},
    )

    target_inv = TargetStoreAdapter().export_inventory()
    result = reconcile_inventories(source_inv, target_inv)
    assert result.status == ReconciliationStatus.DUPLICATE_SOURCE_IDENTITY


def test_unsupported_schema_version_rejected(tmp_path):
    """Prove that legacy SQLite databases with unsupported schema versions raise UnsupportedSchemaError."""
    db_file = tmp_path / "bad_schema.db"
    conn = sqlite3.connect(str(db_file))
    with conn:
        conn.execute("CREATE TABLE schema_version (version INTEGER)")
        conn.execute("INSERT INTO schema_version VALUES (99)")
    conn.close()

    with pytest.raises(UnsupportedSchemaError, match="Unsupported legacy schema version 99"):
        inventory_legacy_sqlite(str(db_file), expected_schema_version=1)


def test_rerun_idempotency(legacy_db):
    """Prove that running migration multiple times creates zero duplicate target records."""
    source_inv = inventory_legacy_sqlite(legacy_db)
    target_store = TargetStoreAdapter()

    manifest1 = migrate_legacy_data(source_inv, target_store)
    assert len(manifest1.target_ids_created) == 3

    # Re-run migration
    manifest2 = migrate_legacy_data(source_inv, target_store)
    assert len(manifest2.target_ids_created) == 0  # No new records created!

    target_inv = target_store.export_inventory()
    result = reconcile_inventories(source_inv, target_inv)
    assert result.is_match is True


def test_read_only_source_behavior(legacy_db):
    """Prove that legacy SQLite access is strictly read-only and prevents writes."""
    uri = f"file:{legacy_db}?mode=ro"
    ro_conn = sqlite3.connect(uri, uri=True)
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute("INSERT INTO legacy_products VALUES ('p3', 'Fake', 1, 'digest')")
    ro_conn.close()


def test_rollback_manifest_completeness_and_safety(legacy_db):
    """Prove that rollback removes only target records created in manifest and leaves source untouched."""
    source_inv = inventory_legacy_sqlite(legacy_db)
    target_store = TargetStoreAdapter()
    manifest = migrate_legacy_data(source_inv, target_store)

    assert target_store.exists("product_intelligence", "p1")
    assert target_store.exists("video_factory", "v1")

    # Roll back
    removed = rollback_migration(manifest, target_store)
    assert removed == 3
    assert not target_store.exists("product_intelligence", "p1")
    assert not target_store.exists("video_factory", "v1")

    # Verify source database is 100% intact
    source_inv_after = inventory_legacy_sqlite(legacy_db)
    assert source_inv_after.total_count == 3
    assert source_inv_after.overall_checksum == source_inv.overall_checksum
