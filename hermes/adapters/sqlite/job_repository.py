import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, List
from hermes.domain.job import Job, JobStatus
from hermes.ports.job_repository import JobRepository


class SQLiteJobRepository(JobRepository):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initialize_database()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize_database(self):
        from hermes.adapters.sqlite.schema_v2 import apply_schema_v2
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            apply_schema_v2(conn)
        finally:
            conn.close()

    def _now_iso(self) -> str:
        return datetime.utcnow().isoformat()

    def submit(self, job: Job) -> None:
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("""
                INSERT INTO jobs (id, task_name, status, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (job.id, job.task_name, job.status.name, job.created_at.isoformat(), job.updated_at.isoformat(), json.dumps(job.payload)))
            conn.commit()
        finally:
            conn.close()

    def claim(self, worker_id: str, lease_duration_seconds: int) -> Optional[Job]:
        now = datetime.utcnow()
        lease_expiry = now + timedelta(seconds=lease_duration_seconds)
        
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            job_row = conn.execute("""
                SELECT id, task_name, status, created_at, updated_at, payload, worker_id, lease_expires_at
                FROM jobs
                WHERE (status = ? OR (status = ? AND lease_expires_at < ?))
                ORDER BY created_at ASC
                LIMIT 1
            """, (JobStatus.QUEUED.name, JobStatus.RUNNING.name, now.isoformat())).fetchone()
            
            if not job_row:
                return None
            
            job_id = job_row["id"]
            conn.execute("""
                UPDATE jobs
                SET status = ?, worker_id = ?, lease_expires_at = ?, updated_at = ?
                WHERE id = ?
            """, (JobStatus.RUNNING.name, worker_id, lease_expiry.isoformat(), now.isoformat(), job_id))
            conn.commit()
            
            return self.get_job(job_id)
        finally:
            conn.close()

    def complete(self, job_id: str, result: dict) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                UPDATE jobs
                SET status = ?, result_json = ?, updated_at = ?
                WHERE id = ?
            """, (JobStatus.SUCCEEDED.name, json.dumps(result), datetime.utcnow(), job_id))
            conn.commit()
        finally:
            conn.close()

    def fail(self, job_id: str, error_message: str) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                UPDATE jobs
                SET status = ?, error = ?, updated_at = ?
                WHERE id = ?
            """, (JobStatus.FAILED.name, error_message, datetime.utcnow(), job_id))
            conn.commit()
        finally:
            conn.close()

    def retry(self, job_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                UPDATE jobs
                SET status = ?, worker_id = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ?
            """, (JobStatus.QUEUED.name, datetime.utcnow(), job_id))
            conn.commit()
        finally:
            conn.close()

    def cancel(self, job_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                UPDATE jobs
                SET status = ?, updated_at = ?
                WHERE id = ?
            """, (JobStatus.CANCELLED.name, datetime.utcnow(), job_id))
            conn.commit()
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[Job]:
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row: return None
            return self._row_to_job(row)
        finally:
            conn.close()

    def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM jobs WHERE status = ?", (status.name,)).fetchall()
            return [self._row_to_job(row) for row in rows]
        finally:
            conn.close()

    def _row_to_job(self, row) -> Job:
        return Job(
            id=row["id"],
            task_name=row["task_name"],
            status=JobStatus[row["status"]],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            payload=json.loads(row["payload"]) if row["payload"] else {},
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            worker_id=row["worker_id"],
            lease_expires_at=datetime.fromisoformat(row["lease_expires_at"]) if row["lease_expires_at"] else None
        )
