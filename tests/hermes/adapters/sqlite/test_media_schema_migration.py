import sqlite3
from pathlib import Path

import pytest

from hermes.adapters.sqlite import schema_v10, schema_v11, video_factory_repository


def test_v10_to_v11_migration_preserves_data_and_adds_f2_f5_fields(tmp_path):
    db_path = tmp_path / "hermes.sqlite"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    # Apply v10 schema and insert data
    schema_v10.apply_schema_v10(connection)
    connection.execute(
        "INSERT INTO video_factory_projects (id, owner_user_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("p1", "owner1", "draft", "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z"),
    )
    connection.commit()

    # Apply v11 migration
    schema_v11.apply_schema_v11(connection)
    
    # Verify new columns exist and data is preserved
    row = connection.execute("SELECT * FROM video_factory_projects WHERE id = 'p1'").fetchone()
    assert row["id"] == "p1"
    assert "storyboard_json" in row.keys()
    assert "timeline_json" in row.keys()
    assert "draft_video_asset_id" in row.keys()

    connection.close()


def test_generated_assets_table_is_created(tmp_path):
    db_path = tmp_path / "hermes.sqlite"
    connection = sqlite3.connect(db_path)
    schema_v11._create_generated_assets_table(connection)
    cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_factory_generated_assets'")
    assert cursor.fetchone() is not None
    connection.close()


def test_rollback_from_v11_is_not_supported_yet():
    # Placeholder for rollback test
    pass
