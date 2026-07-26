import pytest
from pathlib import Path
from hermes.migration.legacy_backfill import backfill, MigrationReport


def test_backfill_is_idempotent(tmp_path):
    # Create a mock legacy root
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    (legacy_root / "project1").mkdir()
    (legacy_root / "project1" / "knowledge.md").write_text("# Knowledge")
    
    # First backfill
    report1 = backfill(None, legacy_root)
    assert report1.imported_projects == 1
    
    # Second backfill should be idempotent (skip duplicates)
    report2 = backfill(None, legacy_root)
    assert report2.imported_projects == 1  # Should not double count


def test_backfill_handles_missing_legacy_root(tmp_path):
    non_existent = tmp_path / "does_not_exist"
    report = backfill(None, non_existent)
    assert report.skipped == 1
    assert len(report.error_messages) > 0


def test_backfill_counts_knowledge_files(tmp_path):
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    (legacy_root / "knowledge").mkdir()
    (legacy_root / "knowledge" / "lesson1.md").write_text("# Lesson 1")
    (legacy_root / "knowledge" / "lesson2.md").write_text("# Lesson 2")
    
    report = backfill(None, legacy_root)
    assert report.imported_knowledge == 2
