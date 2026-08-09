# Knowledge Maintenance Runbook (K4)

This runbook describes operational use of the K4 Knowledge Maintenance
capability.

## Concepts

| Concept | Description |
|---------|-------------|
| `needs_reanalysis` | A lesson is flagged for re-review. Approval status is preserved. |
| `conflict` | A recorded disagreement between a lesson and another lesson/source. |
| `revision` | A proposed change to an existing lesson's content. |
| `supersession` | Old lesson marked superseded by new lesson; old is preserved. |

States:

| Conflict | Lesson approval |
|----------|-----------------|
| `open` | still applies |
| `resolved` | addressed by revision/rejection |
| `dismissed` | false positive |

## Health Check

Run maintenance health check:

```python
service = KnowledgeMaintenanceService(conn_factory)
reanalyzes = service.list_needs_reanalysis("owner_id")
conflicts = service.list_open_conflicts("owner_id")
```

Healthy state: 0 open conflicts, 0 needs_reanalysis items.

## Detect Source Content Change

```python
result = service.detect_source_change(
    owner="owner_id",
    source_id="src_xyz",
    new_content_text="Updated content",
)
# result["changed"] == True if hash differs
```

If changed, register new version:

```python
version = service.register_source_version(
    owner="owner_id",
    source_id="src_xyz",
    content_text="Updated content",
)
```

## Mark Lesson For Reanalysis

```python
service.mark_lesson_needs_reanalysis(
    owner="owner_id",
    lesson_id="kb_abc",
    reason="Source content changed",
    actor="owner_id",
)
```

Approval status is preserved.

## Record Conflict

```python
conflict = service.record_conflict(
    owner="owner_id",
    lesson_id="kb_abc",
    reason="New evidence contradicts approved claim",
    conflicting_source_id="src_new",
)
```

Idempotent: same conflict recorded twice returns the original.

## Propose Revision

```python
proposal = service.create_revision_proposal(
    owner="owner_id",
    original_lesson_id="kb_abc",
    proposed_title="Revised Title",
    proposed_content="New evidence shows...",
    reason="Updated source content",
    actor="owner_id",
)
```

Proposal is stored in `detail_json.revision_proposals` as `pending`.

## Supersession (Old Lesson Preserved)

When a new lesson replaces an approved one:

```python
service.supersede_lesson(
    owner="owner_id",
    old_lesson_id="kb_v1",
    new_lesson_id="kb_v2",
    reason="v2 reflects updated evidence",
    actor="owner_id",
)
```

Old lesson remains in DB with:
- `is_current = 0`
- `superseded_by = "kb_v2"`
- `superseded_at = "<timestamp>"`
- Still retrievable via `get_lesson_history`

FTS5 is updated: old removed, new added (if new is approved).

## Get Lesson History

```python
history = service.get_lesson_history("owner_id", "kb_abc")
# {
#     "found": True,
#     "lesson_id": "kb_abc",
#     "is_current": True/False,
#     "superseded_by": "kb_v2" or None,
#     "events": [...],
#     "supersession_in": [...],
#     "supersession_out": [...],
#     "conflicts": [...],
# }
```

## Manual Reanalysis Clearance

When you determine a lesson is still valid:

```python
service.clear_needs_reanalysis(
    owner="owner_id",
    lesson_id="kb_abc",
    actor="owner_id",  # explicit authorization
    reason="Manual review: original evidence still supports this lesson",
)
```

Requires explicit actor + reason (HITL).

## Conflict Resolution

```python
service.resolve_conflict(
    owner="owner_id",
    conflict_id="conf_xyz",
    actor="owner_id",
    resolution_note="Resolved by revision v2",
)
# or:
service.dismiss_conflict(
    owner="owner_id",
    conflict_id="conf_xyz",
    actor="owner_id",
    resolution_note="False positive",
)
```

## Owner Isolation

All maintenance operations are owner-scoped. Owner A cannot:
- Mark Owner B's lesson for reanalysis
- Record conflict on Owner B's lesson
- View Owner B's history
- Resolve Owner B's conflicts

## Idempotency

- Source re-registration: same content hash → returns existing version
- Conflict recording: same (lesson, conflicting_*) → returns existing conflict_id
- Revision proposals: stored in detail_json, indexed by revision_id

## What K4 Does NOT Do

- Does NOT auto-approve revisions
- Does NOT auto-supersede old lessons
- Does NOT auto-reject trusted knowledge
- Does NOT delete old/superseded lessons
- Does NOT add a background scheduler (manual/on-demand only)
- Does NOT add vector DB or embeddings

## HITL Authorization

Any operation that modifies trusted knowledge state requires explicit HITL:

- `knowledge_clear_reanalysis` — requires explicit actor + reason
- `knowledge_resolve_conflict` — requires explicit actor
- `knowledge_propose_revision` — proposed; HITL approves via normal flow
- Supersession — initiated by Hermes; HITL confirms by approving v2

## Fresh Session Reconstruction

All maintenance state is in SQLite. A fresh process can:

```python
service = KnowledgeMaintenanceService(conn_factory)
reanalyzes = service.list_needs_reanalysis("owner_id")
conflicts = service.list_open_conflicts("owner_id")
history = service.get_lesson_history("owner_id", "kb_abc")
```

No chat/session state required.

## Common Workflows

### Source Change → Lesson Reanalysis

1. Detect source content change (hash differs)
2. Register new source version (auto-increment)
3. List lessons depending on source (not auto-linked yet — manual or Hermes-assisted)
4. Mark affected lessons `needs_reanalysis`
5. Hermes reviews lesson + new evidence
6. Propose revision OR clear reanalysis
7. HITL approval

### Contradictory Evidence → Conflict + Revision

1. New contradictory source registered
2. Record conflict for affected lesson
3. Hermes reads lesson + new source + old evidence
4. Propose revision if needed
5. Pending proposal waits for HITL
6. HITL approves → old lesson updated to revision OR old lesson marked superseded by new

### Historical Source Superseded by Current

1. New current spec replaces historical
2. Register new current source
3. Historical source remains in DB (provenance)
4. Affected lessons may need reanalysis
5. Current knowledge (using new source) is favored in retrieval
6. Historical knowledge remains accessible via history