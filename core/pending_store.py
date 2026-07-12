import json
import threading
from datetime import datetime, timedelta
from pathlib import Path


class PendingStore:
    """
    Persist pending video links and files to disk as JSON.
    Thread-safe for asyncio handlers that may interleave sync store calls.
    """

    def __init__(self, store_path: str = "data/pending_state.json"):
        self.store_path = Path(store_path)
        if not self.store_path.is_absolute():
            self.store_path = Path(__file__).resolve().parent.parent / self.store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def set_link(self, chat_id: int, url: str) -> None:
        with self._lock:
            data = self._load()
            data.setdefault("links", {})[str(chat_id)] = {
                "url": url,
                "saved_at": self._now(),
            }
            self._save(data)

    def get_link(self, chat_id: int) -> str | None:
        with self._lock:
            entry = self._load().get("links", {}).get(str(chat_id))
            return entry.get("url") if isinstance(entry, dict) else None

    def clear_link(self, chat_id: int) -> None:
        with self._lock:
            data = self._load()
            data.setdefault("links", {}).pop(str(chat_id), None)
            self._save(data)

    def set_file(self, chat_id: int, file_info: dict) -> None:
        with self._lock:
            data = self._load()
            entry = dict(file_info or {})
            entry["saved_at"] = self._now()
            data.setdefault("files", {})[str(chat_id)] = entry
            self._save(data)

    def get_file(self, chat_id: int) -> dict | None:
        with self._lock:
            entry = self._load().get("files", {}).get(str(chat_id))
            return dict(entry) if isinstance(entry, dict) else None

    def clear_file(self, chat_id: int) -> None:
        with self._lock:
            data = self._load()
            data.setdefault("files", {}).pop(str(chat_id), None)
            self._save(data)

    def cleanup_expired(self, ttl_hours: int = 24) -> int:
        """Remove entries older than ttl_hours and return the number removed."""
        cutoff = datetime.now() - timedelta(hours=ttl_hours)
        removed = 0
        with self._lock:
            data = self._load()
            for section in ["links", "files"]:
                entries = data.setdefault(section, {})
                for chat_id, entry in list(entries.items()):
                    saved_at = self._parse_time(entry.get("saved_at") if isinstance(entry, dict) else "")
                    if not saved_at or saved_at < cutoff:
                        entries.pop(chat_id, None)
                        removed += 1
            if removed:
                self._save(data)
        return removed

    def _load(self) -> dict:
        if not self.store_path.exists():
            return {"links": {}, "files": {}}
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return {"links": {}, "files": {}}
        if not isinstance(data, dict):
            return {"links": {}, "files": {}}
        data.setdefault("links", {})
        data.setdefault("files", {})
        return data

    def _save(self, data: dict) -> None:
        tmp_path = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.store_path)

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _parse_time(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None
