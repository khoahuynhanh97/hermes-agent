from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, Any, Optional
import uuid

class JobStatus(Enum):
    QUEUED = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    CANCELLED = auto()

@dataclass
class Job:
    id: str
    task_name: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    worker_id: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    attempt: int = 0
    max_attempts: int = 3
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @staticmethod
    def new(task_name: str, payload: Dict[str, Any]) -> 'Job':
        now = datetime.utcnow()
        return Job(
            id=str(uuid.uuid4()),
            task_name=task_name,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            payload=payload
        )
