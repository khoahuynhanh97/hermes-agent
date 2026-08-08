# K6 — Knowledge Export & Backup — FINAL REPORT

**Date**: 2026-08-07  
**Status**: ✅ **K6 FULL PASS**

---

## 1. K6 Status

✅ **K6 FULL PASS**

- SQLite DB backup (full point-in-time copy) — verified
- Structured JSON export — verified with integrity hash
- Markdown export — verified (incl. untitled-lesson notes)
- Restore to temporary DB — verified with parity check
- Owner isolation — verified
- No secret leakage — verified (no secrets in export)
- Repeat export safe — deterministic hash
- Canonical source remains SQLite + FTS5

---

## 2. Backup Formats

| Format | Purpose | Restore-capable |
|--------|---------|-----------------|
| SQLite copy (`.sqlite`) | Full DB backup | Yes (replace DB file) |
| JSON export (`.json`) | Structured, portable, verifiable | Yes (temp DB) |
| Markdown export (`.md`) | Human-readable current approved | No (display only) |

---

## 3. Export Structure

```json
{
  "metadata": {
    "export_timestamp": "...",
    "schema_version": 12,
    "exported_owner_user_id": "owner",
    "record_counts": { "sources": N, "lessons": N, ... },
    "content_hash": "sha256..."
  },
  "sources": [...],
  "lessons": [...],
  "evidence": [...],
  "conflicts": [...],
  "source_versions": [...],
  "supersession_lineage": [...]
}
```

Lessons include `source_url` (joined from sources) so restore preserves
provenance.

---

## 4. Restore Verification

- `KnowledgeRestoreService.restore_from_json(owner, path, new_owner=None)`
  - rejects newer schema versions
  - rejects tampered exports (content hash mismatch)
  - restores lessons + sources into a temporary DB
  - `new_owner_user_id` remaps ownership
- `verify_restore_parity(source_store, restored_db, owner)` checks:
  - lesson count parity
  - approved count parity
  - source count parity
  - FTS retrieval parity

---

## 5. Integrity Checks

- Content hash = SHA-256 over the export payload (excluding metadata)
- Recalculated on restore; mismatch → `ValueError`
- Deterministic serialization (`sort_keys=True`) makes hash stable across runs
- Record counts included in metadata

---

## 6. Files Changed

**Created**:
- `hermes/utils/json_helpers.py` — shared canonical JSON helpers (break circular import)
- `hermes/application/knowledge_export.py` — export/backup/restore services
- `tests/hermes/application/test_k6_export_backup.py` — 8 tests
- `docs/runbooks/knowledge-backup-k6.md` — backup runbook
- `docs/K6_FINAL_REPORT.md` — this report

**Modified**:
- `hermes/knowledge.py` — `list_sources()`, `get_entry_evidence()`, `import_legacy_entry()` fixes; use `json_helpers`
- `hermes/application/knowledge_maintenance.py` — use `json_helpers` (break circular import)
- `mcp_servers/knowledge/server.py` — 4 K6 tools (backup/export/export_markdown/restore_verify)

**No schema change** — reuses schema v12.

---

## 7. Tests

### K6 (8 tests, all passing)

| Test | Covers |
|------|--------|
| `test_k6_backup_database` | SQLite backup integrity |
| `test_k6_export_json_structure_and_integrity` | JSON structure + content hash |
| `test_k6_export_markdown_readable_content` | Markdown content + untitled note |
| `test_k6_export_owner_isolation` | Owner-scoped export |
| `test_k6_restore_from_json_basic_parity` | Restore + parity |
| `test_k6_restore_to_new_owner` | Owner remap on restore |
| `test_k6_restore_json_integrity_check` | Tamper detection |
| `test_k6_restore_markdown_not_supported` | Markdown is display-only |

### Combined focused regression

```
68 passed in 6.34s
```

Includes K3 (11) + K4 (22) + K5 (11) + K6 (8) + Video Factory (13) + duplicate check (3).

### Pre-existing failure (unchanged)

`tests/hermes/test_learning_service.py::test_worker_builds_atomic_lessons_from_source_bound_analysis`
— `JobWorker.build_learning_result` never existed; unrelated to K-series work.

### Checks

- `py_compile` on all changed modules: PASS
- MCP coupling scan: no Video Factory → Video MCP / cross-MCP imports

---

## 8. Recommended Backup Cadence

Weekly (personal project):

```bash
hermes cron create "0 8 * * 1" \
  "Run knowledge backup: create a SQLite DB copy and a structured JSON export into the configured backup directory, then report the artifact paths." \
  --name "k6-knowledge-backup" \
  --skill knowledge-learning \
  --deliver local
```

Optional monthly JSON export (see runbook). No high-frequency schedules.

---

## 9. Architecture Confirmation

✅ SQLite = canonical Knowledge state  
✅ FTS5 = approved retrieval  
✅ backup/export = secondary artifact only (never source of truth)  
✅ `unified_index.json` = compatibility snapshot only  
✅ Hermes = reasoning  
✅ Knowledge MCP = capability boundary  
✅ HITL unchanged  
✅ No new agent  
✅ No vector DB  
✅ Owner scope preserved through export/restore  

---

## 10. Remaining Issues

None introduced by K6. The single pre-existing test failure is documented and
unrelated.

---

## 11. K7 Recommendation

**One evidence-backed next step**: **K7 — Retrieval Evaluation (optional)** only
if FTS5 shows concrete misses. Current evidence (K3 + K6) shows FTS5 sufficient
for approved-only retrieval; no immediate change needed.

Do not begin K7 automatically.

---

✅ **K6 FULL PASS** — export and restore verification both pass.
