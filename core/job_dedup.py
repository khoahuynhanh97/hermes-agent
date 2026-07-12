import hashlib
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


logger = logging.getLogger(__name__)


class JobDedup:
    """
    Detect and prevent duplicate jobs based on source + mode hash.
    Persisted to disk and automatically expired after the configured TTL.
    """

    def __init__(self, store_path: str = "data/job_dedup.json", ttl_hours: int = 48):
        self.store_path = Path(store_path)
        if not self.store_path.is_absolute():
            self.store_path = Path(__file__).resolve().parent.parent / self.store_path
        self.ttl_hours = ttl_hours
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._key_locks = {}

    def make_key(self, source_value: str, mode: str, chat_id: int = 0) -> str:
        """SHA256(chat_id + source_value + mode)[:16]."""
        source = self.normalize_source(source_value)
        return hashlib.sha256(f"{chat_id}:{source}:{mode}".encode()).hexdigest()[:16]

    def normalize_source(self, source_value: str) -> str:
        source = (source_value or "").strip()
        if not source.lower().startswith(("http://", "https://")):
            return source
        try:
            parts = urlsplit(source)
            query = [
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
            ]
            normalized = urlunsplit((
                parts.scheme.lower(),
                parts.netloc.lower(),
                parts.path.rstrip("/"),
                urlencode(query, doseq=True),
                "",
            ))
            return normalized
        except Exception:
            return source

    @contextmanager
    def lock_for(self, source_value: str, mode: str, chat_id: int = 0):
        key = self.make_key(source_value, mode, chat_id)
        with self._lock:
            lock = self._key_locks.setdefault(key, threading.Lock())
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def is_duplicate(self, source_value: str, mode: str, chat_id: int = 0) -> dict | None:
        """
        Return job info if it exists and has not expired.
        Return None when no entry exists or the entry has expired.
        """
        key = self.make_key(source_value, mode, chat_id)
        with self._lock:
            data = self._load()
            entry = data.get("jobs", {}).get(key)
            if not entry:
                return None
            if self._is_expired(entry):
                data.get("jobs", {}).pop(key, None)
                self._save(data)
                return None
            return dict(entry)

    def register(self, source_value: str, mode: str, job_id: str, chat_id: int = 0) -> None:
        """Register a new job in the dedup store."""
        key = self.make_key(source_value, mode, chat_id)
        with self._lock:
            data = self._load()
            data.setdefault("jobs", {})[key] = {
                "job_id": job_id,
                "chat_id": chat_id,
                "source_value": self.normalize_source(source_value),
                "mode": mode,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._save(data)

    def create_or_duplicate(self, source_value: str, mode: str, chat_id: int, create_job):
        """Single-process atomic duplicate check + job creation + registration."""
        with self.lock_for(source_value, mode, chat_id):
            existing = self.is_duplicate(source_value, mode, chat_id=chat_id)
            if existing:
                return {
                    "duplicate": True,
                    "existing_job_id": existing["job_id"],
                    "message": f"Job nay da duoc tao luc {existing['created_at']}",
                }
            job = create_job()
            self.register(source_value, mode, job["job_id"], chat_id=chat_id)
            return job

    def cleanup_expired(self) -> int:
        removed = 0
        with self._lock:
            data = self._load()
            jobs = data.setdefault("jobs", {})
            for key, entry in list(jobs.items()):
                if self._is_expired(entry):
                    jobs.pop(key, None)
                    removed += 1
            if removed:
                self._save(data)
        return removed

    def _load(self) -> dict:
        if not self.store_path.exists():
            return {"jobs": {}}
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Job dedup store is corrupt; continuing without blocking jobs: %s", exc)
            return {"jobs": {}}
        if not isinstance(data, dict):
            return {"jobs": {}}
        data.setdefault("jobs", {})
        return data

    def _save(self, data: dict) -> None:
        tmp_path = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.store_path)

    def _is_expired(self, entry: dict) -> bool:
        created_at = self._parse_time(entry.get("created_at", ""))
        if not created_at:
            return True
        return created_at < datetime.now() - timedelta(hours=self.ttl_hours)

    @staticmethod
    def _parse_time(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None
