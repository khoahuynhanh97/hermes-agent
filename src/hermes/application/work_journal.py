from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes.runtime_layout import get_work_journal_dir


class RunStatus(str, Enum):
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JournalStep:
    name: str
    status: RunStatus = RunStatus.STARTED
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class WorkJournalEntry:
    run_id: str
    project_id: Optional[str] = None
    product_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    resource_pack_lock_id: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    status: RunStatus = RunStatus.STARTED
    steps: List[JournalStep] = field(default_factory=list)
    tool_job_result_summary: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    repeated_error_fingerprint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for step in data.get("steps", []):
            if isinstance(step["status"], Enum):
                step["status"] = step["status"].value
        if isinstance(data.get("status"), Enum):
            data["status"] = data["status"].value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkJournalEntry:
        data = dict(data)
        if "status" in data and isinstance(data["status"], str):
            data["status"] = RunStatus(data["status"])
        if "steps" in data:
            steps = []
            for raw_step in data["steps"]:
                step = dict(raw_step)
                if "status" in step and isinstance(step["status"], str):
                    step["status"] = RunStatus(step["status"])
                steps.append(JournalStep(**step))
            data["steps"] = steps
        return cls(**data)


class WorkJournal:
    def __init__(self, journal_dir: Path):
        self.journal_dir = journal_dir
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    def _get_entry_path(self, run_id: str) -> Path:
        return self.journal_dir / f"{run_id}.json"

    def record_entry(self, entry: WorkJournalEntry) -> None:
        path = self._get_entry_path(entry.run_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, indent=2, default=str)

    def get_entry(self, run_id: str) -> Optional[WorkJournalEntry]:
        path = self._get_entry_path(run_id)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return WorkJournalEntry.from_dict(data)
        return None

    def list_entries(self) -> List[WorkJournalEntry]:
        entries = []
        for f in self.journal_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file)
                entries.append(WorkJournalEntry.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                # Log error or skip malformed entries
                pass
        return entries
