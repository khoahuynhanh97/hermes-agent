# K4 — KNOWLEDGE MAINTENANCE & REANALYSIS — FINAL REPORT

**Date**: 2026-08-06  
**Status**: ✅ **K4 FULL PASS**

---

## 1. K4 Status

✅ **K4 FULL PASS**

Maintenance operations implemented and tested:
- Source change detection (content hash)
- Source versioning (preserved history)
- needs_reanalysis (preserves approval status)
- Conflict recording (open/resolved/dismissed)
- Revision proposals (durable, pending)
- Supersession (preserves old lesson)
- History retrieval (full lineage)
- Owner isolation enforced
- FTS5 current-only behavior

---

## 2. Maintenance Architecture

```
Hermes (reason_combo via 9Router)
      ↓
knowledge-learning Skill (procedure)
      ↓
Knowledge MCP (capability boundary)
      ↓
KnowledgeMaintenanceService (application)
      ↓
SQLite (canonical, schema v12)

Components:
- SourceVersionTable (preserves content hash history)
- KnowledgeConflicts (open/resolved/dismissed)
- LessonSupersession (lineage tracking)
- Lessons.superseded_by / is_current / revision_of (K4 columns)
```

---

## 3. Source Change Detection

Implemented via content hash:
- `register_source_version`: idempotent — same hash returns existing version
- `detect_source_change`: compares new content hash with latest version
- Returns: `changed`, `is_new`, `previous_hash`, `previous_version`

Used to identify affected lessons (manual or Hermes-assisted).

---

## 4. Source Versioning

`source_versions` table tracks:
- `version_id` (PK)
- `source_id`, `owner_user_id`
- `content_hash`
- `version_number` (auto-increment)
- `registered_at`
- `reference_uri`
- `metadata_json`

Multiple versions preserved. Old versions remain queryable for history.

---

## 5. needs_reanalysis Semantics

Existing semantic extended via maintenance service:
- `mark_lesson_needs_reanalysis`: flags lesson + records event
- **Approval status preserved** (does NOT change status)
- `reanalysis_count` incremented
- `reanalysis_reason` stored in detail_json

Clearance:
- `clear_needs_reanalysis` requires explicit actor + reason (HITL)
- Records `reanalysis_cleared` event

---

## 6. Conflict Model

`knowledge_conflicts` table:
- `conflict_id` (PK)
- `owner_user_id`
- `lesson_id`
- `conflicting_lesson_id` (optional)
- `conflicting_source_id` (optional)
- `reason`
- `status`: open | resolved | dismissed
- `created_at`, `resolved_at`, `resolution_note`

Idempotent on (lesson, conflicting_*) tuple.
Owner isolation enforced (cannot record conflict on owner's lesson).

---

## 7. Reanalysis Flow

```
lesson marked needs_reanalysis
  ↓
Hermes reads:
  - current lesson
  - original evidence
  - new source/evidence
  - conflicting lessons
  ↓
Hermes proposes:
  - keep unchanged → clear_needs_reanalysis
  - revise → propose_revision
  - supersede → create new + supersede_lesson
  - reject (current still valid)
  ↓
durable proposal
  ↓
HITL authorization
```

Hermes never directly mutates trusted knowledge without approval.

---

## 8. Revision / Supersession

**Revision**:
- Stored in original lesson's `detail_json.revision_proposals`
- Status: pending → approved | rejected | superseded
- Original lesson unchanged until HITL acts

**Supersession**:
- Non-destructive: old lesson remains
- Old: `is_current=0`, `superseded_by=<new_id>`, `superseded_at=<ts>`
- New: indexed in FTS5 (if approved)
- Old: removed from FTS5 but queryable via history

Lineage:
- `lesson_supersession` table tracks old→new relationships
- `get_lesson_history` returns full lineage

---

## 9. HITL

Explicit authorization required for:
- `knowledge_clear_reanalysis` (actor + reason)
- `knowledge_resolve_conflict` (actor)
- `knowledge_propose_revision` (proposed; HITL confirms via normal lifecycle)
- Supersession (HITL approves the new lesson which triggers supersession)

For tests: explicit test-domain authorization used.

---

## 10. Knowledge History

`get_lesson_history(lesson_id)` returns:
```python
{
    "found": True,
    "lesson_id": "kb_abc",
    "title": "...",
    "status": "approved",
    "is_current": True/False,
    "superseded_by": "kb_v2" or None,
    "superseded_at": "...",
    "revision_of": "kb_v1" or None,
    "needs_reanalysis": True/False,
    "events": [approval, reanalysis, supersession events],
    "supersession_in": [other lessons superseded by this],
    "supersession_out": [this lesson's supersession targets],
    "conflicts": [all conflicts for this lesson],
}
```

Full lineage traceable.

---

## 11. Search Semantics

**FTS5 behavior**:
- `get_approved_context` returns current approved lessons
- Superseded lessons are removed from FTS5 (when supersession occurs)
- Pending/rejected excluded

**History queries**:
- Superseded lessons accessible via `get_lesson_history`
- `is_current` flag distinguishes current from superseded
- `superseded_by` points to replacement

---

## 12. FTS Integrity

Verified via tests:
- `test_k4_fts_prefers_current_approved`: superseded lessons not returned
- `test_k4_supersede_lesson_preserves_old`: old lesson still retrievable via `get_entry`
- `test_k4_fresh_session_reconstructs_full_history`: full reconstruction

---

## 13. Data Health

Maintenance metrics via `knowledge_health`:
- `needs_reanalysis_count`
- `open_conflicts_count`
- List of items

**Manual health check pattern**:
```python
service = KnowledgeMaintenanceService(conn_factory)
reanalyzes = service.list_needs_reanalysis(owner)
conflicts = service.list_open_conflicts(owner)
# Iterate, address each
```

No autonomous fix; human/Hermes decides.

---

## 14. Fresh Session Acceptance

✅ `test_k4_fresh_session_reconstructs_full_history`

Fresh process can reconstruct:
- Source versions
- Conflict metadata
- Reanalysis flags
- Supersession lineage
- All events

No chat/session state required.

---

## 15. Cross-Capability Reuse

**Demonstrated potential**:
- Hermes retrieves current approved creative principles
- Hermes proposes revision based on new evidence
- Knowledge MCP → Hermes → Video Factory MCP (orchestrated, not coupled)

K4 maintenance ensures cross-capability reuse always uses **current** approved knowledge, not stale/superseded.

---

## 16. Research Fallback

Architecture supports:
- Hermes → Knowledge search → insufficient → Hermes → Research MCP
- New source → Hermes synthesis → revision proposal

No MCP-to-MCP orchestration. Hermes orchestrates both.

---

## 17. Owner Isolation

Tests verify:
- `test_k4_owner_isolation_mark_reanalysis`: wrong owner cannot flag
- `test_k4_owner_isolation_conflict`: wrong owner cannot record
- `test_k4_owner_isolation_history`: wrong owner cannot view

All maintenance operations owner-scoped at SQL level.

---

## 18. Tests

### Focused K4 Tests (NEW)

`tests/hermes/application/test_k4_maintenance.py` — **22 tests, all passing**:

- Source: hash change, versioning, idempotent
- Reanalysis: mark, list, clear (with auth)
- Conflict: record (idempotent), list, resolve, dismiss
- Revision: create proposal, supersede (preserves old), history
- Owner isolation: 3 tests
- FTS: prefers current
- Health: metrics
- Non-destructive: rejected revision does not damage current
- Multiple lessons: maintenance scales

### Combined Focused Tests

```
52 passed in 5.39s
```

Includes: 22 K4 + 11 K3 + 9 Video Factory + 7 Knowledge duplicate check + 3 others

---

## 19. Pre-existing Failure

**Identified (unchanged from K3)**: 
`tests/hermes/test_learning_service.py::LearningServiceTests::test_worker_builds_atomic_lessons_from_source_bound_analysis`

**Failure**: `AttributeError: type object 'JobWorker' has no attribute 'build_learning_result'`

**Evidence of pre-existing**:
- Created in commit `6aeb26a9b5fe9797d606dd1bbb55a4aa7867c30d`
- References non-existent `JobWorker.build_learning_result` method
- Unrelated to K4 (or any K-series work)

K4 does not introduce new failures.

---

## 20. Files Changed

**Created**:
- `hermes/adapters/sqlite/schema_v12.py` (K4 schema migration)
- `hermes/application/knowledge_maintenance.py` (maintenance service)
- `tests/hermes/application/test_k4_maintenance.py` (22 tests)
- `docs/runbooks/knowledge-maintenance-k4.md` (runbook)
- `docs/K4_FINAL_REPORT.md` (this report)

**Modified**:
- `hermes/db.py` (added v12 migration)
- `hermes/knowledge.py` (extended `_row_to_entry` with K4 fields)
- `mcp_servers/knowledge/server.py` (added 9 maintenance tools)
- `skills/knowledge-learning/SKILL.md` (updated to v2.0.0 with maintenance procedure)

---

## 21. Remaining Technical Debt

1. **Pre-existing test failures** (unrelated to K4):
   - `test_learning_service.py::test_worker_builds_atomic_lessons_from_source_bound_analysis` (JobWorker method missing)
   - Other pre-existing failures (job_repository schema, etc.)

2. **No background scheduler**: K4 is manual/on-demand; future K5 may add scheduling.

3. **No automated source-change watcher**: source changes detected on explicit re-registration only.

---

## 22. Recommended K5

**Choose one evidence-backed next step**:

### Option A: Automated Maintenance Scheduler

- Background job to detect source changes and flag reanalysis
- Scheduled data-health checks
- Notification of maintenance items

**Evidence**: K4 demonstrates manual flow works; automation would reduce manual overhead.

### Option B: Cross-Knowledge Conflict Detection

- Auto-detect similar but potentially conflicting lessons via FTS5 similarity
- Suggest conflict recording when overlap detected
- Cluster lessons by topic to surface contradictions

**Evidence**: K4 conflict model exists; auto-detection would improve coverage.

### ✅ Recommended: **Option A — Automated Maintenance Scheduler**

Manual K4 works but is reactive. A scheduled maintenance pass would:
- Detect stale sources automatically
- Flag affected lessons for reanalysis
- Surface open conflicts for review

This closes the maintenance loop and prevents knowledge rot.

---

## 23. Architecture Confirmation

✅ **Hermes** = reasoning/reanalysis (sole general-purpose brain)  
✅ **Knowledge Skill** = procedure (`skills/knowledge-learning/` v2.0.0)  
✅ **Knowledge MCP** = capability boundary (`mcp_servers/knowledge/` with 15 tools)  
✅ **SQLite** = canonical state (`hermes.db`, schema v12)  
✅ **FTS5** = current approved retrieval (`lesson_fts`)  
✅ **HITL** = trust boundary (explicit actor + reason)  
✅ **Research** = evidence acquisition (separate MCP)  
✅ **JSON** = compatibility snapshot only (no authority)  
✅ **Memory ≠ Knowledge** (Memory in `messages`/`memories` tables)  
✅ **Graphify ≠ Knowledge** (separate scope)

**No MCP-to-MCP coupling.**  
**No second Agent.**  
**No vector DB added.**

---

## 24. V1 Closure

✅ **K4 FULL PASS**

The Knowledge system now supports long-lived maintenance:
- Source content changes detected via hash
- Source history preserved
- Lessons marked for reanalysis (approval preserved)
- Conflicts recorded (idempotent)
- Revisions proposed (durable, pending)
- Supersession preserves old lessons
- Full history retrievable
- Owner isolation enforced
- FTS5 consistent
- Fresh session reconstruction works

**Architecture invariants preserved.**

---

*Report completed: 2026-08-06T18:15:00Z*  
*K4 Operations: COMPLETE*  
*Test Status: 52/53 focused tests passing (1 pre-existing failure unchanged)*  
*Architecture: COMPLIANT*