# Product Intelligence to Video Factory Flow: Legacy Data Migration & Reconciliation Runbook

## Overview
This runbook guides operators through the safe, non-destructive migration and cryptographic reconciliation of legacy Product Intelligence and Video Factory artifacts into the Gate 5 durable storage model.

## Safety Guarantees & Invariants
1. **Read-Only Legacy Access**: All legacy database readers open SQLite connections strictly with `file:...?...mode=ro`.
2. **Zero Deletions on Source**: Source records, legacy SQLite files, uploaded raw media, and intermediate research outputs are never modified, renamed, or deleted.
3. **Cryptographic Reconciliation**: Every entity's `(opaque_id, version, digest)` tuple is sorted and checksummed via SHA-256 to guarantee 100% data fidelity.
4. **Idempotent Reruns**: Migrations can be executed multiple times safely without generating duplicate target records or mutating existing valid data.
5. **Target-Only Rollback**: Rollback operations are strictly scoped to removing records explicitly created in the corresponding `MigrationManifest`.

## Reconciliation Status Matrix
| Status | Meaning | Action |
|---|---|---|
| `MATCH` | Source and target entity counts and checksums match 100%. | Migration verified; proceed to traffic cutover. |
| `MISSING_TARGET_ROW` | Source entity was not migrated to target. | Re-run `migrate_legacy_data()`. |
| `MISMATCH_CHECKSUM` | Entity digest/version discrepancy between source and target. | Inspect corrupted target record and re-migrate. |
| `DUPLICATE_SOURCE_IDENTITY` | Multiple source records share identical `(context, id)`. | Clean source anomalies or deduplicate before migration. |
| `UNSUPPORTED_SCHEMA` | Source database has an unexpected schema version. | Run pre-migration schema upgrade. |

## Migration Execution
```python
from hermes_personal.migration import (
    inventory_legacy_sqlite,
    reconcile_inventories,
    migrate_legacy_data,
    rollback_migration,
    TargetStoreAdapter,
)

# 1. Inventory legacy store (strictly read-only)
source_inv = inventory_legacy_sqlite("/path/to/legacy_store.db")

# 2. Run idempotent migration
target_store = TargetStoreAdapter()
manifest = migrate_legacy_data(source_inv, target_store)

# 3. Verify reconciliation
target_inv = target_store.export_inventory()
recon_result = reconcile_inventories(source_inv, target_inv)
assert recon_result.is_match, f"Reconciliation failed: {recon_result.discrepancies}"
```

## Rollback Procedure
If target store verification fails or rollback is required:
```python
# Rollback removes ONLY target records recorded in the manifest
removed_count = rollback_migration(manifest, target_store)
print(f"Cleaned up {removed_count} target records. Source data remains 100% untouched.")
```
