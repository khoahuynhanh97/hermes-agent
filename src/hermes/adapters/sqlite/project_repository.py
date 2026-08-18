from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from hermes.adapters.sqlite.schema_v2 import apply_schema_v2
from hermes.domain.results import Result
from hermes.ports.project_repository import Project, ProjectRepository


class SQLiteProjectRepository(ProjectRepository):
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        with sqlite3.connect(self.db_path) as conn:
            apply_schema_v2(conn)

    def create(self, name: str, filesystem_root: str = "") -> Result[Project]:
        project_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO projects (id, name, filesystem_root, created_at, updated_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (project_id, name, filesystem_root, now, now, True),
                )
                conn.commit()
            return Result.success(self.get(project_id).value)  # type: ignore  # type: ignore
        except sqlite3.IntegrityError:
            return Result.failure("conflict", f"Project with name {name} already exists.")
        except Exception as e:
            return Result.failure("unavailable", str(e))

    def get(self, project_id: str) -> Result[Project]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
                row = cursor.fetchone()
                if row:
                    return Result.success(Project(
                        id=row["id"],
                        name=row["name"],
                        filesystem_root=row["filesystem_root"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        is_active=bool(row["is_active"]),
                    ))
                return Result.failure("not_found", f"Project with ID {project_id} not found.")
        except Exception as e:
            return Result.failure("unavailable", str(e))

    def list_active(self) -> Result[list[Project]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM projects WHERE is_active = 1")
                rows = cursor.fetchall()
                projects = [
                    Project(
                        id=row["id"],
                        name=row["name"],
                        filesystem_root=row["filesystem_root"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        is_active=bool(row["is_active"]),
                    )
                    for row in rows
                ]
                return Result.success(projects)
        except Exception as e:
            return Result.failure("unavailable", str(e))

    def archive(self, project_id: str) -> Result[None]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE projects SET is_active = 0, updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), project_id),
                )
                conn.commit()
                if cursor.rowcount == 0:
                    return Result.failure("not_found", f"Project with ID {project_id} not found.")
                return Result.success(None)
        except Exception as e:
            return Result.failure("unavailable", str(e))
