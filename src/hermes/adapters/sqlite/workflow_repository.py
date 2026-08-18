"""SQLite WorkflowRepository implementation for Prompt Studio."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from hermes.domain.prompt_studio import PromptStudioStep, PromptStudioWorkflow, WorkflowStep
from hermes.domain.results import Result


class SQLiteWorkflowRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_workflows (
                    project_id TEXT PRIMARY KEY,
                    steps_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get(self, project_id: str) -> Result[PromptStudioWorkflow]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM prompt_workflows WHERE project_id = ?", (project_id,))
                row = cursor.fetchone()
                if row:
                    raw_steps = json.loads(row["steps_json"])
                    steps = [
                        WorkflowStep(
                            name=PromptStudioStep(item["name"]),
                            content=item.get("content", {}),
                            approved=item.get("approved", False),
                            updated_at=item.get("updated_at", ""),
                        )
                        for item in raw_steps
                    ]
                    return Result.success(PromptStudioWorkflow(project_id=project_id, steps=steps))
                return Result.failure("not_found", f"Workflow for project {project_id} not found")
        except Exception as e:
            return Result.failure("unavailable", str(e))

    def save(self, workflow: PromptStudioWorkflow) -> Result[PromptStudioWorkflow]:
        try:
            steps_data = [
                {
                    "name": s.name.value if hasattr(s.name, "value") else str(s.name),
                    "content": s.content,
                    "approved": s.approved,
                    "updated_at": s.updated_at,
                }
                for s in workflow.steps
            ]
            steps_json = json.dumps(steps_data, ensure_ascii=False)
            now = steps_data[0]["updated_at"] if steps_data else ""

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO prompt_workflows (project_id, steps_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        steps_json = excluded.steps_json,
                        updated_at = excluded.updated_at
                    """,
                    (workflow.project_id, steps_json, now),
                )
                conn.commit()
            return Result.success(workflow)
        except Exception as e:
            return Result.failure("unavailable", str(e))
