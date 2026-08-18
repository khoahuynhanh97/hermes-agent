"""Video Factory F1 structured project state."""

import sqlite3


def apply_schema_v10(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS video_factory_projects (
            id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft', 'resource_ready', 'brief_ready',
                                 'scene_plan_ready', 'ready_for_storyboard')),
            resource_pack_json TEXT NOT NULL DEFAULT '{}',
            raw_idea_json TEXT NOT NULL DEFAULT '{}',
            creative_brief_json TEXT NOT NULL DEFAULT '{}',
            scene_plan_json TEXT NOT NULL DEFAULT '{}',
            brief_approval TEXT NOT NULL DEFAULT 'pending',
            scene_plan_approval TEXT NOT NULL DEFAULT 'pending',
            resource_version INTEGER NOT NULL DEFAULT 0 CHECK(resource_version >= 0),
            idea_version INTEGER NOT NULL DEFAULT 0 CHECK(idea_version >= 0),
            brief_version INTEGER NOT NULL DEFAULT 0 CHECK(brief_version >= 0),
            scene_version INTEGER NOT NULL DEFAULT 0 CHECK(scene_version >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_user_id, id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_factory_owner_updated "
        "ON video_factory_projects(owner_user_id, updated_at DESC)"
    )
    connection.commit()
