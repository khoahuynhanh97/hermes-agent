"""Video Factory F2-F5 extended state: Storyboard, Video Generation, Timeline, Final Export.

Migration strategy: on fresh DBs (where v10 just created the table), we need to
recreate with the extended columns. On existing v10 DBs, we ALTER TABLE to add columns.
Since both paths need a final table with the extended CHECK constraint, we use a
safe approach: drop-and-recreate.
"""

import sqlite3


def apply_schema_v12(connection: sqlite3.Connection) -> None:
    """K4 maintenance: add conflict tracking, source versioning, supersession lineage."""
    
    # Conflict metadata table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_conflicts (
            conflict_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            lesson_id TEXT NOT NULL,
            conflicting_lesson_id TEXT,
            conflicting_source_id TEXT,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK(status IN ('open', 'resolved', 'dismissed')),
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolution_note TEXT,
            UNIQUE(owner_user_id, conflict_id)
        )
        """
    )
    
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_kc_lesson "
        "ON knowledge_conflicts(lesson_id, status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_kc_owner "
        "ON knowledge_conflicts(owner_user_id, status)"
    )
    
    # Source version history (preserves source hash lineage)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_versions (
            version_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            version_number INTEGER NOT NULL DEFAULT 1,
            registered_at TEXT NOT NULL,
            reference_uri TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(owner_user_id, source_id, version_number)
        )
        """
    )
    
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_sv_source "
        "ON source_versions(source_id, owner_user_id)"
    )
    
    # Lesson supersession lineage (preserves old lesson when superseded)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS lesson_supersession (
            lineage_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            old_lesson_id TEXT NOT NULL,
            new_lesson_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(owner_user_id, old_lesson_id, new_lesson_id)
        )
        """
    )
    
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_ls_old "
        "ON lesson_supersession(old_lesson_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_ls_new "
        "ON lesson_supersession(new_lesson_id)"
    )
    
    # Add supersession/active flag to lessons table (if column missing)
    existing_columns = [
        row[1]
        for row in connection.execute("PRAGMA table_info(lessons)").fetchall()
    ]
    
    if "superseded_by" not in existing_columns:
        connection.execute(
            "ALTER TABLE lessons ADD COLUMN superseded_by TEXT"
        )
    
    if "superseded_at" not in existing_columns:
        connection.execute(
            "ALTER TABLE lessons ADD COLUMN superseded_at TEXT"
        )
    
    if "revision_of" not in existing_columns:
        connection.execute(
            "ALTER TABLE lessons ADD COLUMN revision_of TEXT"
        )
    
    if "is_current" not in existing_columns:
        connection.execute(
            "ALTER TABLE lessons ADD COLUMN is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1))"
        )
    
    # Backfill: mark all existing approved lessons as current
    connection.execute(
        "UPDATE lessons SET is_current = 1 WHERE is_current IS NULL OR status != 'approved'"
    )
    
    connection.commit()