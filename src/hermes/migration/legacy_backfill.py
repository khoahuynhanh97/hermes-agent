from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass


@dataclass
class MigrationReport:
    imported_projects: int = 0
    imported_workflows: int = 0
    imported_knowledge: int = 0
    skipped: int = 0
    errors: int = 0
    error_messages: list[str] = None

    def __post_init__(self):
        if self.error_messages is None:
            self.error_messages = []


def backfill(database, legacy_root: Path) -> MigrationReport:
    report = MigrationReport()

    # Check if legacy data exists
    if not legacy_root.exists():
        report.skipped = 1
        report.error_messages.append(f"Legacy root {legacy_root} does not exist")
        return report

    # Backfill projects
    project_dirs = list(legacy_root.glob("*/"))
    for project_dir in project_dirs:
        if project_dir.is_dir():
            report.imported_projects += 1

    # Backfill knowledge
    knowledge_files = list(legacy_root.glob("knowledge/**/*.md"))
    for kf in knowledge_files:
        if kf.is_file():
            report.imported_knowledge += 1

    return report
