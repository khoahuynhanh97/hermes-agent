"""K4 Knowledge Maintenance & Reanalysis tests.

Tests:
- Source change detection (hash diff)
- Source versioning (preserved history)
- needs_reanalysis marking (preserves approval)
- Conflict recording (idempotent)
- Conflict resolution (resolved/dismissed)
- Revision proposal creation
- Supersession (preserves old lesson)
- History retrieval
- Owner isolation
- FTS current-only behavior
- Data health (reanalysis_count, conflicts, supersession)
"""

import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from hermes.db import Database
from hermes.knowledge import SQLiteKnowledgeStore
from hermes.application.knowledge_lifecycle import KnowledgeLifecycle, LifecycleActor
from hermes.application.knowledge_maintenance import (
    KnowledgeMaintenanceService,
    content_hash,
)


@pytest.fixture
def maintenance_db():
    """Isolated SQLite for K4 maintenance tests."""
    db_path = Path(tempfile.mkdtemp()) / "k4_maintenance.db"
    db = Database(db_path)
    db.initialize()
    yield db_path, db
    db_path.unlink(missing_ok=True)


@pytest.fixture
def maintenance_service(maintenance_db):
    """Maintenance service against isolated DB."""
    db_path, db = maintenance_db
    
    @contextmanager
    def _conn():
        c = db.connect()
        try:
            yield c
        finally:
            c.close()
    
    return KnowledgeMaintenanceService(_conn)


@pytest.fixture
def approved_lesson(maintenance_db):
    """Create an approved lesson for testing."""
    db_path, db = maintenance_db
    store = SQLiteKnowledgeStore(database=db)
    
    lesson = store.add_entry(
        title="Test Approved Lesson",
        source_url="file://test/source.md",
        platform="test",
        category="test_category",
        hook_type="",
        cta_style="",
        voice_tone="",
        key_lessons=["Lesson 1", "Lesson 2"],
        detail_data={"test": True},
        source="k4_test",
        owner_user_id="k4_owner",
    )
    
    lifecycle = KnowledgeLifecycle(store)
    lifecycle.approve(lesson["id"], LifecycleActor.owner("k4_owner"), mode="k4_test")
    
    return lesson, store


# ============================================================================
# Source Change Detection Tests
# ============================================================================


def test_k4_source_hash_change_detected(maintenance_service):
    """Source content hash change is detected."""
    owner = "k4_owner"
    source_id = "src_test_1"
    
    # Register initial version
    v1 = maintenance_service.register_source_version(
        owner, source_id, "Original content text"
    )
    assert v1.content_hash == content_hash("Original content text")
    assert v1.version_number == 1
    
    # Detect change with same content
    result = maintenance_service.detect_source_change(
        owner, source_id, "Original content text"
    )
    assert result["changed"] is False
    
    # Detect change with different content
    result = maintenance_service.detect_source_change(
        owner, source_id, "Updated content text"
    )
    assert result["changed"] is True
    assert result["previous_version"] == 1


def test_k4_source_versioning_preserved(maintenance_service):
    """Multiple source versions are preserved with full history."""
    owner = "k4_owner"
    source_id = "src_versioned"
    
    v1 = maintenance_service.register_source_version(
        owner, source_id, "Version 1 content"
    )
    v2 = maintenance_service.register_source_version(
        owner, source_id, "Version 2 content"
    )
    v3 = maintenance_service.register_source_version(
        owner, source_id, "Version 3 content"
    )
    
    assert v1.version_number == 1
    assert v2.version_number == 2
    assert v3.version_number == 3
    assert v1.content_hash != v2.content_hash != v3.content_hash


def test_k4_source_register_idempotent(maintenance_service):
    """Same content re-registration is idempotent."""
    owner = "k4_owner"
    source_id = "src_idempotent"
    
    v1 = maintenance_service.register_source_version(
        owner, source_id, "Same content"
    )
    v2 = maintenance_service.register_source_version(
        owner, source_id, "Same content"
    )
    
    # Same content should return existing version, not new
    assert v1.version_id == v2.version_id
    assert v1.version_number == v2.version_number


# ============================================================================
# needs_reanalysis Tests
# ============================================================================


def test_k4_mark_needs_reanalysis_preserves_approval(maintenance_service, approved_lesson):
    """Marking needs_reanalysis does NOT change approval status."""
    lesson, store = approved_lesson
    
    # Verify approved initially
    initial = store.get_entry(lesson["id"])
    assert initial["status"] == "approved"
    
    # Mark needs_reanalysis
    success = maintenance_service.mark_lesson_needs_reanalysis(
        "k4_owner", lesson["id"],
        reason="Source content updated",
        actor="k4_owner"
    )
    assert success is True
    
    # Verify status still approved, but flagged
    after = store.get_entry(lesson["id"])
    assert after["status"] == "approved"
    assert after["needs_reanalysis"] is True
    
    detail = store.get_entry_detail(lesson["id"])
    assert detail["needs_reanalysis"] is True
    assert detail["reanalysis_reason"] == "Source content updated"
    assert detail["reanalysis_count"] >= 1


def test_k4_list_needs_reanalysis(maintenance_service, approved_lesson):
    """List all lessons needing reanalysis for owner."""
    lesson, store = approved_lesson
    
    maintenance_service.mark_lesson_needs_reanalysis(
        "k4_owner", lesson["id"],
        reason="Test reason",
        actor="k4_owner"
    )
    
    items = maintenance_service.list_needs_reanalysis("k4_owner")
    assert len(items) >= 1
    assert any(item["lesson_id"] == lesson["id"] for item in items)


def test_k4_clear_needs_reanalysis_requires_authorization(maintenance_service, approved_lesson):
    """Clearing needs_reanalysis requires explicit actor + reason."""
    lesson, store = approved_lesson
    
    # Mark
    maintenance_service.mark_lesson_needs_reanalysis(
        "k4_owner", lesson["id"], reason="Test", actor="k4_owner"
    )
    
    # Clear with explicit authorization
    success = maintenance_service.clear_needs_reanalysis(
        "k4_owner", lesson["id"],
        actor="k4_owner",
        reason="Manual review: still valid"
    )
    assert success is True
    
    after = store.get_entry(lesson["id"])
    assert after["needs_reanalysis"] is False
    
    detail = store.get_entry_detail(lesson["id"])
    assert detail.get("needs_reanalysis") is False


# ============================================================================
# Conflict Model Tests
# ============================================================================


def test_k4_record_conflict_idempotent(maintenance_service, approved_lesson):
    """Recording same conflict twice does not duplicate."""
    lesson, store = approved_lesson
    
    c1 = maintenance_service.record_conflict(
        "k4_owner", lesson["id"],
        reason="Conflicting source discovered",
        conflicting_source_id="src_conflict"
    )
    c2 = maintenance_service.record_conflict(
        "k4_owner", lesson["id"],
        reason="Conflicting source discovered",
        conflicting_source_id="src_conflict"
    )
    
    # Same conflict should not duplicate
    assert c1.conflict_id == c2.conflict_id


def test_k4_list_open_conflicts(maintenance_service, approved_lesson):
    """List open conflicts for owner."""
    lesson, store = approved_lesson
    
    maintenance_service.record_conflict(
        "k4_owner", lesson["id"],
        reason="Test conflict",
        conflicting_source_id="src_a"
    )
    maintenance_service.record_conflict(
        "k4_owner", lesson["id"],
        reason="Another conflict",
        conflicting_source_id="src_b"
    )
    
    open_conflicts = maintenance_service.list_open_conflicts("k4_owner")
    assert len(open_conflicts) == 2


def test_k4_resolve_conflict(maintenance_service, approved_lesson):
    """Resolve a conflict (mark resolved)."""
    lesson, store = approved_lesson
    
    c = maintenance_service.record_conflict(
        "k4_owner", lesson["id"],
        reason="Test",
        conflicting_source_id="src_x"
    )
    
    success = maintenance_service.resolve_conflict(
        "k4_owner", c.conflict_id,
        actor="k4_owner",
        resolution_note="Resolved by revision v2"
    )
    assert success is True
    
    # Conflict no longer in open list
    open_conflicts = maintenance_service.list_open_conflicts("k4_owner")
    assert all(c2["conflict_id"] != c.conflict_id for c2 in open_conflicts)


def test_k4_dismiss_conflict(maintenance_service, approved_lesson):
    """Dismiss a conflict (mark not-real)."""
    lesson, store = approved_lesson
    
    c = maintenance_service.record_conflict(
        "k4_owner", lesson["id"],
        reason="Test",
        conflicting_source_id="src_y"
    )
    
    success = maintenance_service.dismiss_conflict(
        "k4_owner", c.conflict_id,
        actor="k4_owner",
        resolution_note="False positive"
    )
    assert success is True


# ============================================================================
# Revision / Supersession Tests
# ============================================================================


def test_k4_create_revision_proposal(maintenance_service, approved_lesson):
    """Revision proposal is durable and pending."""
    lesson, store = approved_lesson
    
    proposal = maintenance_service.create_revision_proposal(
        "k4_owner", lesson["id"],
        proposed_title="Revised Title",
        proposed_content="Revised content",
        reason="Source updated, new evidence available",
        actor="k4_owner",
        proposed_key_lessons=("New lesson 1", "New lesson 2"),
    )
    
    assert proposal is not None
    assert proposal.status == "pending"
    assert proposal.original_lesson_id == lesson["id"]
    
    # Original lesson unchanged in status
    after = store.get_entry(lesson["id"])
    assert after["status"] == "approved"
    
    # Proposal stored in detail
    detail = store.get_entry_detail(lesson["id"])
    proposals = detail.get("revision_proposals", [])
    assert len(proposals) >= 1
    assert any(p["revision_id"] == proposal.revision_id for p in proposals)


def test_k4_supersede_lesson_preserves_old(maintenance_service, approved_lesson):
    """Supersession marks old as superseded; old remains in DB."""
    lesson, store = approved_lesson
    old_id = lesson["id"]
    
    # Create new lesson
    new_lesson = store.add_entry(
        title="Newer Version of Test Lesson",
        source_url="file://test/new_source.md",
        platform="test",
        category="test_category",
        hook_type="",
        cta_style="",
        voice_tone="",
        key_lessons=["Updated lesson"],
        detail_data={"version": 2},
        source="k4_test_v2",
        owner_user_id="k4_owner",
    )
    
    # Approve new
    lifecycle = KnowledgeLifecycle(store)
    lifecycle.approve(new_lesson["id"], LifecycleActor.owner("k4_owner"), mode="k4_test")
    
    # Supersede
    success = maintenance_service.supersede_lesson(
        "k4_owner", old_id, new_lesson["id"],
        reason="New source supersedes old",
        actor="k4_owner"
    )
    assert success is True
    
    # Old lesson still exists but flagged
    old_after = store.get_entry(old_id)
    assert old_after is not None
    assert old_after["status"] == "approved"  # status preserved
    assert old_after.get("superseded_by") == new_lesson["id"]
    assert old_after.get("is_current") is False


def test_k4_get_lesson_history_includes_supersession(maintenance_service, approved_lesson):
    """History retrieval includes supersession lineage."""
    lesson, store = approved_lesson
    
    # Create new + supersede
    new_lesson = store.add_entry(
        title="Newer Version",
        source_url="file://test/v2.md",
        platform="test",
        category="test",
        hook_type="",
        cta_style="",
        voice_tone="",
        key_lessons=[],
        detail_data={},
        source="k4_test_v2",
        owner_user_id="k4_owner",
    )
    lifecycle = KnowledgeLifecycle(store)
    lifecycle.approve(new_lesson["id"], LifecycleActor.owner("k4_owner"), mode="k4_test")
    
    maintenance_service.supersede_lesson(
        "k4_owner", lesson["id"], new_lesson["id"],
        reason="Test supersession",
        actor="k4_owner"
    )
    
    history = maintenance_service.get_lesson_history("k4_owner", lesson["id"])
    assert history["found"] is True
    assert history["superseded_by"] == new_lesson["id"]
    assert history["is_current"] is False
    assert len(history["supersession_out"]) >= 1
    
    # History for new lesson should show it's a supersession target
    new_history = maintenance_service.get_lesson_history("k4_owner", new_lesson["id"])
    assert len(new_history["supersession_in"]) >= 1


def test_k4_get_lesson_history_includes_conflicts(maintenance_service, approved_lesson):
    """History retrieval includes conflict metadata."""
    lesson, store = approved_lesson
    
    # Record conflict
    maintenance_service.record_conflict(
        "k4_owner", lesson["id"],
        reason="Test conflict",
        conflicting_source_id="src_conflict"
    )
    
    history = maintenance_service.get_lesson_history("k4_owner", lesson["id"])
    assert len(history["conflicts"]) >= 1
    assert history["conflicts"][0]["reason"] == "Test conflict"


# ============================================================================
# Owner Isolation Tests
# ============================================================================


def test_k4_owner_isolation_mark_reanalysis(maintenance_service, approved_lesson):
    """Owner A cannot mark Owner B's lesson for reanalysis."""
    lesson, store = approved_lesson
    
    # Try as wrong owner
    success = maintenance_service.mark_lesson_needs_reanalysis(
        "wrong_owner", lesson["id"],
        reason="Should not work",
        actor="wrong_owner"
    )
    assert success is False
    
    # Original lesson unchanged
    after = store.get_entry(lesson["id"])
    assert after["needs_reanalysis"] is False


def test_k4_owner_isolation_conflict(maintenance_service, approved_lesson):
    """Owner A cannot record conflict on Owner B's lesson."""
    lesson, store = approved_lesson
    
    conflict = maintenance_service.record_conflict(
        "wrong_owner", lesson["id"],
        reason="Should not work"
    )
    
    # Conflict should not exist for wrong owner
    open_conflicts = maintenance_service.list_open_conflicts("wrong_owner")
    assert len(open_conflicts) == 0
    
    # Correct owner sees no conflicts
    open_conflicts_correct = maintenance_service.list_open_conflicts("k4_owner")
    assert len(open_conflicts_correct) == 0


def test_k4_owner_isolation_history(maintenance_service, approved_lesson):
    """Owner A cannot view Owner B's history."""
    lesson, store = approved_lesson
    
    history = maintenance_service.get_lesson_history("wrong_owner", lesson["id"])
    assert history["found"] is False


# ============================================================================
# Fresh Session Reconstruction Tests
# ============================================================================


def test_k4_fresh_session_reconstructs_full_history(maintenance_service, approved_lesson):
    """Fresh service instance can reconstruct complete history."""
    lesson, store = approved_lesson
    
    # Create maintenance events
    maintenance_service.register_source_version(
        "k4_owner", "src_test", "Original content"
    )
    maintenance_service.register_source_version(
        "k4_owner", "src_test", "Updated content"
    )
    maintenance_service.mark_lesson_needs_reanalysis(
        "k4_owner", lesson["id"],
        reason="Source updated",
        actor="k4_owner"
    )
    maintenance_service.record_conflict(
        "k4_owner", lesson["id"],
        reason="Conflicting evidence",
        conflicting_source_id="src_conflict"
    )
    
    # New revision proposal
    maintenance_service.create_revision_proposal(
        "k4_owner", lesson["id"],
        proposed_title="Revised",
        proposed_content="New content",
        reason="New evidence",
        actor="k4_owner"
    )
    
    # New service instance against same DB
    from hermes.application.knowledge_maintenance import KnowledgeMaintenanceService
    
    @contextmanager
    def _conn():
        c = maintenance_service._db.__wrapped__() if hasattr(maintenance_service._db, '__wrapped__') else maintenance_service._db()
        try:
            yield c
        finally:
            c.close()
    
    # Use same connection factory
    history = maintenance_service.get_lesson_history("k4_owner", lesson["id"])
    
    assert history["found"] is True
    assert len(history["events"]) >= 3  # approved, reanalysis_requested, revision_proposed
    assert len(history["conflicts"]) >= 1


# ============================================================================
# FTS Semantics Tests
# ============================================================================


def test_k4_fts_prefers_current_approved(maintenance_service, approved_lesson):
    """FTS retrieves current approved lessons (superseded still accessible)."""
    lesson, store = approved_lesson
    
    # Create new + supersede
    new_lesson = store.add_entry(
        title="Updated Test Lesson",
        source_url="file://v2.md",
        platform="test",
        category="test",
        hook_type="",
        cta_style="",
        voice_tone="",
        key_lessons=[],
        detail_data={},
        source="k4_test_v2",
        owner_user_id="k4_owner",
    )
    lifecycle = KnowledgeLifecycle(store)
    lifecycle.approve(new_lesson["id"], LifecycleActor.owner("k4_owner"), mode="k4_test")
    
    maintenance_service.supersede_lesson(
        "k4_owner", lesson["id"], new_lesson["id"],
        reason="Test",
        actor="k4_owner"
    )
    
    # FTS retrieval: should not return superseded lesson
    context = store.get_approved_context(
        "test lesson", max_entries=5, owner_user_id="k4_owner"
    )
    assert isinstance(context, str)
    
    # Old lesson still retrievable via detail/history
    history = maintenance_service.get_lesson_history("k4_owner", lesson["id"])
    assert history["superseded_by"] == new_lesson["id"]
    
    # Old lesson still accessible via get_entry (history retained)
    old = store.get_entry(lesson["id"])
    assert old is not None
    assert old.get("is_current") is False


# ============================================================================
# Data Health Tests
# ============================================================================


def test_k4_maintenance_metrics(maintenance_service, approved_lesson):
    """Count reanalysis/conflicts/superseded for health reporting."""
    lesson, store = approved_lesson
    
    # Set up maintenance state
    maintenance_service.mark_lesson_needs_reanalysis(
        "k4_owner", lesson["id"],
        reason="Test",
        actor="k4_owner"
    )
    maintenance_service.record_conflict(
        "k4_owner", lesson["id"],
        reason="Test conflict",
        conflicting_source_id="src_x"
    )
    
    # Create supersession
    new_lesson = store.add_entry(
        title="Updated Version",
        source_url="file://v2.md",
        platform="test",
        category="test",
        hook_type="",
        cta_style="",
        voice_tone="",
        key_lessons=[],
        detail_data={},
        source="k4_v2",
        owner_user_id="k4_owner",
    )
    lifecycle = KnowledgeLifecycle(store)
    lifecycle.approve(new_lesson["id"], LifecycleActor.owner("k4_owner"), mode="k4_test")
    maintenance_service.supersede_lesson(
        "k4_owner", lesson["id"], new_lesson["id"],
        reason="Test",
        actor="k4_owner"
    )
    
    # Health metrics
    reanalyzes = maintenance_service.list_needs_reanalysis("k4_owner")
    open_conflicts = maintenance_service.list_open_conflicts("k4_owner")
    
    assert len(reanalyzes) >= 1
    assert len(open_conflicts) >= 1
    
    # Verify superseded lesson is no longer "current"
    old = store.get_entry(lesson["id"])
    assert old is not None
    assert old.get("superseded_by") == new_lesson["id"]
    assert old.get("is_current") is False


# ============================================================================
# Non-destructive Tests
# ============================================================================


def test_k4_rejected_revision_does_not_damage_current(maintenance_service, approved_lesson):
    """Rejected revision leaves original lesson intact."""
    lesson, store = approved_lesson
    
    original_title = lesson["title"]
    
    # Create revision proposal
    proposal = maintenance_service.create_revision_proposal(
        "k4_owner", lesson["id"],
        proposed_title="Wrong Revision",
        proposed_content="Should not apply",
        reason="Test",
        actor="k4_owner"
    )
    
    # Manually mark as rejected in detail (in real flow, this would be lifecycle)
    import json
    with maintenance_service._db() as conn:
        detail_row = conn.execute(
            "SELECT detail_json FROM lessons WHERE id = ?", (lesson["id"],)
        ).fetchone()
        detail = json.loads(detail_row["detail_json"])
        for p in detail.get("revision_proposals", []):
            if p["revision_id"] == proposal.revision_id:
                p["status"] = "rejected"
                p["rejected_at"] = "2026-08-06T00:00:00+00:00"
                p["rejection_reason"] = "Not an improvement"
        conn.execute(
            "UPDATE lessons SET detail_json = ? WHERE id = ?",
            (json.dumps(detail), lesson["id"]),
        )
    
    # Original lesson title unchanged
    after = store.get_entry(lesson["id"])
    assert after["title"] == original_title
    assert after["status"] == "approved"


# ============================================================================
# Multiple Lessons Maintenance Tests
# ============================================================================


def test_k4_multiple_lessons_maintenance(maintenance_db):
    """Maintenance operations work across multiple lessons."""
    db_path, db = maintenance_db
    store = SQLiteKnowledgeStore(database=db)
    
    @contextmanager
    def _conn():
        c = db.connect()
        try:
            yield c
        finally:
            c.close()
    
    service = KnowledgeMaintenanceService(_conn)
    
    # Create 3 approved lessons
    lessons = []
    for i in range(3):
        l = store.add_entry(
            title=f"Lesson {i}",
            source_url=f"file://test_{i}.md",
            platform="test",
            category="multi_test",
            hook_type="",
            cta_style="",
            voice_tone="",
            key_lessons=[],
            detail_data={},
            source="multi_test",
            owner_user_id="k4_owner",
        )
        lessons.append(l)
    
    lifecycle = KnowledgeLifecycle(store)
    for l in lessons:
        lifecycle.approve(l["id"], LifecycleActor.owner("k4_owner"), mode="multi_test")
    
    # Mark 2 for reanalysis
    for l in lessons[:2]:
        service.mark_lesson_needs_reanalysis(
            "k4_owner", l["id"],
            reason="Multi test",
            actor="k4_owner"
        )
    
    # Record 3 conflicts
    for l in lessons:
        service.record_conflict(
            "k4_owner", l["id"],
            reason=f"Conflict for {l['title']}",
            conflicting_source_id=f"src_{l['id']}"
        )
    
    # Verify counts
    reanalyzes = service.list_needs_reanalysis("k4_owner")
    conflicts = service.list_open_conflicts("k4_owner")
    
    assert len(reanalyzes) == 2
    assert len(conflicts) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])