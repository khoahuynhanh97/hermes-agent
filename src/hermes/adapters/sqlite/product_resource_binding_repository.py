"""SQLite adapter for ProjectResourceBinding repository."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from hermes.db import Database
from hermes.domain.product_resource import ProjectResourceBinding
from hermes.ports.product_resource_binding_repository import ProjectResourceBindingRepository


class SQLiteProjectResourceBindingRepository(ProjectResourceBindingRepository):
    def __init__(self, database: Database):
        self.database = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_resource_bindings (
                    binding_id TEXT PRIMARY KEY,
                    project_id TEXT UNIQUE NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    resource_lock_id TEXT NOT NULL,
                    resource_pack_id TEXT NOT NULL,
                    manifest_digest TEXT NOT NULL,
                    lock_version INTEGER NOT NULL,
                    canonical_product_id TEXT NOT NULL,
                    variant_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resource_pack_locks (
                    lock_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    resource_pack_id TEXT NOT NULL,
                    resource_pack_version INTEGER NOT NULL,
                    manifest_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(owner_user_id, resource_pack_id, resource_pack_version, manifest_digest)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS binding_audit_events (
                    event_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    previous_lock_id TEXT,
                    new_lock_id TEXT,
                    manifest_digest TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save(
        self,
        binding: ProjectResourceBinding,
        owner_user_id: str,
        resource_lock_id: str,
        allow_rebind: bool = False,
    ) -> None:
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        binding_id = f"bind_{binding.project_id}"
        action = "rebind" if allow_rebind else "bind"
        with self.database.connect() as conn:
            existing = conn.execute(
                "SELECT resource_lock_id FROM project_resource_bindings WHERE project_id = ? AND status = 'active'",
                (binding.project_id,),
            ).fetchone()

            previous_lock_id = existing[0] if existing else None
            if existing and not allow_rebind:
                raise ValueError("PROJECT_BINDING_ALREADY_EXISTS: Use explicit rebind command to replace binding")

            conn.execute(
                """
                INSERT OR REPLACE INTO project_resource_bindings (
                    binding_id, project_id, owner_user_id, resource_lock_id,
                    resource_pack_id, manifest_digest, lock_version,
                    canonical_product_id, variant_id, created_at, updated_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    binding_id,
                    binding.project_id,
                    owner_user_id,
                    resource_lock_id,
                    binding.resource_pack_id,
                    binding.manifest_digest,
                    binding.lock_version,
                    binding.canonical_product_id,
                    binding.variant_id,
                    now,
                    now,
                    "active",
                ),
            )
            conn.execute(
                """
                INSERT INTO binding_audit_events (
                    event_id, project_id, owner_user_id, action,
                    previous_lock_id, new_lock_id, manifest_digest, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex[:8]}",
                    binding.project_id,
                    owner_user_id,
                    action,
                    previous_lock_id,
                    resource_lock_id,
                    binding.manifest_digest,
                    now,
                ),
            )
            conn.commit()

    def get_by_project_id(self, project_id: str) -> Optional[ProjectResourceBinding]:
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                SELECT project_id, source_system, resource_pack_id, lock_version, manifest_digest, canonical_product_id, variant_id
                FROM (
                    SELECT project_id, 'product_intelligence' AS source_system, resource_pack_id, lock_version, manifest_digest, canonical_product_id, variant_id
                    FROM project_resource_bindings
                    WHERE project_id = ? AND status = 'active'
                )
                """,
                (project_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ProjectResourceBinding(
                project_id=row[0],
                source_system=row[1],
                resource_pack_id=row[2],
                lock_version=row[3],
                manifest_digest=row[4],
                canonical_product_id=row[5],
                variant_id=row[6],
            )

    def unbind(self, project_id: str, owner_user_id: str) -> None:
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE project_resource_bindings SET status = 'unbound', updated_at = ? WHERE project_id = ?",
                (now, project_id),
            )
            conn.execute(
                """
                INSERT INTO binding_audit_events (
                    event_id, project_id, owner_user_id, action,
                    previous_lock_id, new_lock_id, manifest_digest, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"evt_{uuid.uuid4().hex[:8]}", project_id, owner_user_id, "unbind", None, None, "", now),
            )
            conn.commit()

    def archive(self, project_id: str, owner_user_id: str) -> None:
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE project_resource_bindings SET status = 'archived', updated_at = ? WHERE project_id = ?",
                (now, project_id),
            )
            conn.execute(
                """
                INSERT INTO binding_audit_events (
                    event_id, project_id, owner_user_id, action,
                    previous_lock_id, new_lock_id, manifest_digest, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"evt_{uuid.uuid4().hex[:8]}", project_id, owner_user_id, "archive", None, None, "", now),
            )
            conn.commit()

    def save_resource_pack_lock(self, payload_json: str, owner_user_id: str, resource_pack_id: str, resource_pack_version: int, manifest_digest: str) -> str:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as conn:
            existing = conn.execute(
                """
                SELECT lock_id FROM resource_pack_locks
                WHERE owner_user_id = ? AND resource_pack_id = ? AND resource_pack_version = ? AND manifest_digest = ?
                """,
                (owner_user_id, resource_pack_id, resource_pack_version, manifest_digest),
            ).fetchone()
            if existing:
                return str(existing["lock_id"])
            count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM resource_pack_locks
                WHERE owner_user_id = ? AND resource_pack_id = ? AND resource_pack_version = ?
                """,
                (owner_user_id, resource_pack_id, resource_pack_version),
            ).fetchone()["count"]
            lock_id = f"lock_{resource_pack_id}_v{resource_pack_version}_{int(count) + 1}"
            conn.execute(
                """
                INSERT INTO resource_pack_locks (
                    lock_id, owner_user_id, resource_pack_id, resource_pack_version,
                    manifest_digest, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (lock_id, owner_user_id, resource_pack_id, resource_pack_version, manifest_digest, payload_json, now),
            )
            conn.commit()
            return lock_id
