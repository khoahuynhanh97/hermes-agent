"""Video Factory F2-F5 extended state: Storyboard, Video Generation, Timeline, Final Export.

Migration strategy: on fresh DBs (where v10 just created the table), we need to
recreate with the extended columns. On existing v10 DBs, we ALTER TABLE to add columns.
Since both paths need a final table with the extended CHECK constraint, we use a
safe approach: drop-and-recreate.
"""

import sqlite3


def apply_schema_v11(connection: sqlite3.Connection) -> None:
    """Extend video_factory_projects with F2-F5 fields and add new tables."""
    
    # Check if table exists
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='video_factory_projects'"
    ).fetchone() is not None
    
    if not table_exists:
        # Fresh DB - create with v11 schema directly
        connection.execute(
            """
            CREATE TABLE video_factory_projects (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK(status IN ('draft', 'resource_ready', 'brief_ready',
                                     'scene_plan_ready', 'ready_for_storyboard',
                                     'storyboard_ready', 'storyboard_approved',
                                     'scenes_generated', 'timeline_ready',
                                     'draft_video_ready', 'ready_to_publish')),
                resource_pack_json TEXT NOT NULL DEFAULT '{}',
                raw_idea_json TEXT NOT NULL DEFAULT '{}',
                creative_brief_json TEXT NOT NULL DEFAULT '{}',
                scene_plan_json TEXT NOT NULL DEFAULT '{}',
                storyboard_json TEXT NOT NULL DEFAULT '{}',
                generated_scenes_json TEXT NOT NULL DEFAULT '[]',
                timeline_json TEXT NOT NULL DEFAULT '{}',
                draft_video_asset_id TEXT,
                final_video_asset_id TEXT,
                brief_approval TEXT NOT NULL DEFAULT 'pending',
                scene_plan_approval TEXT NOT NULL DEFAULT 'pending',
                final_approval TEXT NOT NULL DEFAULT 'pending',
                final_approval_notes TEXT NOT NULL DEFAULT '',
                resource_version INTEGER NOT NULL DEFAULT 0 CHECK(resource_version >= 0),
                idea_version INTEGER NOT NULL DEFAULT 0 CHECK(idea_version >= 0),
                brief_version INTEGER NOT NULL DEFAULT 0 CHECK(brief_version >= 0),
                scene_version INTEGER NOT NULL DEFAULT 0 CHECK(scene_version >= 0),
                storyboard_version INTEGER NOT NULL DEFAULT 0 CHECK(storyboard_version >= 0),
                video_generation_version INTEGER NOT NULL DEFAULT 0 CHECK(video_generation_version >= 0),
                timeline_version INTEGER NOT NULL DEFAULT 0 CHECK(timeline_version >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(owner_user_id, id)
            )
            """
        )
        # Drop and recreate index to ensure it exists
        connection.execute("DROP INDEX IF EXISTS idx_video_factory_owner_updated")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_video_factory_owner_updated "
            "ON video_factory_projects(owner_user_id, updated_at DESC)"
        )
        _create_generated_assets_table(connection)
        connection.commit()
        return
    
    # Table exists - check if already migrated
    existing_columns = [
        row[1] 
        for row in connection.execute("PRAGMA table_info(video_factory_projects)").fetchall()
    ]
    
    if "storyboard_json" in existing_columns:
        # Already migrated
        _create_generated_assets_table(connection)
        connection.commit()
        return
    
    # Existing v10 table - need to migrate
    # SQLite doesn't support DROP CONSTRAINT, so we recreate the table
    connection.execute(
        """
        CREATE TABLE video_factory_projects_v11 (
            id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft', 'resource_ready', 'brief_ready',
                                 'scene_plan_ready', 'ready_for_storyboard',
                                 'storyboard_ready', 'storyboard_approved',
                                 'scenes_generated', 'timeline_ready',
                                 'draft_video_ready', 'ready_to_publish')),
            resource_pack_json TEXT NOT NULL DEFAULT '{}',
            raw_idea_json TEXT NOT NULL DEFAULT '{}',
            creative_brief_json TEXT NOT NULL DEFAULT '{}',
            scene_plan_json TEXT NOT NULL DEFAULT '{}',
            storyboard_json TEXT NOT NULL DEFAULT '{}',
            generated_scenes_json TEXT NOT NULL DEFAULT '[]',
            timeline_json TEXT NOT NULL DEFAULT '{}',
            draft_video_asset_id TEXT,
            final_video_asset_id TEXT,
            brief_approval TEXT NOT NULL DEFAULT 'pending',
            scene_plan_approval TEXT NOT NULL DEFAULT 'pending',
            final_approval TEXT NOT NULL DEFAULT 'pending',
            final_approval_notes TEXT NOT NULL DEFAULT '',
            resource_version INTEGER NOT NULL DEFAULT 0 CHECK(resource_version >= 0),
            idea_version INTEGER NOT NULL DEFAULT 0 CHECK(idea_version >= 0),
            brief_version INTEGER NOT NULL DEFAULT 0 CHECK(brief_version >= 0),
            scene_version INTEGER NOT NULL DEFAULT 0 CHECK(scene_version >= 0),
            storyboard_version INTEGER NOT NULL DEFAULT 0 CHECK(storyboard_version >= 0),
            video_generation_version INTEGER NOT NULL DEFAULT 0 CHECK(video_generation_version >= 0),
            timeline_version INTEGER NOT NULL DEFAULT 0 CHECK(timeline_version >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_user_id, id)
        )
        """
    )
    
    connection.execute(
        """
        INSERT INTO video_factory_projects_v11 (
            id, owner_user_id, status,
            resource_pack_json, raw_idea_json, creative_brief_json, scene_plan_json,
            storyboard_json, generated_scenes_json, timeline_json,
            draft_video_asset_id, final_video_asset_id,
            brief_approval, scene_plan_approval, final_approval, final_approval_notes,
            resource_version, idea_version, brief_version, scene_version,
            storyboard_version, video_generation_version, timeline_version,
            created_at, updated_at
        )
        SELECT 
            id, owner_user_id, status,
            resource_pack_json, raw_idea_json, creative_brief_json, scene_plan_json,
            '{}', '[]', '{}',
            NULL, NULL,
            brief_approval, scene_plan_approval, 'pending', '',
            resource_version, idea_version, brief_version, scene_version,
            0, 0, 0,
            created_at, updated_at
        FROM video_factory_projects
        """
    )
    
    connection.execute("DROP TABLE video_factory_projects")
    connection.execute("ALTER TABLE video_factory_projects_v11 RENAME TO video_factory_projects")
    
    # Recreate index
    connection.execute("DROP INDEX IF EXISTS idx_video_factory_owner_updated")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_factory_owner_updated "
        "ON video_factory_projects(owner_user_id, updated_at DESC)"
    )
    
    _create_generated_assets_table(connection)
    connection.commit()


def _create_generated_assets_table(connection: sqlite3.Connection) -> None:
    """Create generated assets tracking table."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS video_factory_generated_assets (
            asset_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL CHECK(artifact_type IN ('frame_image', 'scene_video', 'draft_video', 'final_video')),
            artifact_id TEXT NOT NULL,
            artifact_version INTEGER NOT NULL,
            storage_key TEXT NOT NULL,
            mime_type TEXT,
            checksum_sha256 TEXT NOT NULL,
            provider TEXT,
            provider_generation_id TEXT,
            width INTEGER,
            height INTEGER,
            duration_seconds REAL,
            generation_params_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(owner_user_id, asset_id)
        )
        """
    )
    
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_vf_assets_project "
        "ON video_factory_generated_assets(project_id, artifact_type)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_vf_assets_job "
        "ON video_factory_generated_assets(job_id)"
    )
