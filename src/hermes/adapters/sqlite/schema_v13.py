"""Video Factory publication state (Publishing1)."""

import sqlite3


def apply_schema_v13(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS publications (
            publication_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            post_id TEXT,
            status TEXT NOT NULL DEFAULT 'not_published'
                CHECK(status IN ('not_published', 'uploading', 'processing', 'published', 'failed')),
            caption TEXT NOT NULL DEFAULT '',
            published_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_user_id, project_id, platform)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_publications_owner "
        "ON publications(owner_user_id, updated_at DESC)"
    )

    # Add ab_variants_json column to video_factory_projects if missing (for A/B testing support)
    existing_columns = [
        row[1]
        for row in connection.execute("PRAGMA table_info(video_factory_projects)").fetchall()
    ]
    if "ab_variants_json" not in existing_columns:
        connection.execute(
            "ALTER TABLE video_factory_projects ADD COLUMN ab_variants_json TEXT NOT NULL DEFAULT '{}'"
        )

    connection.commit()
