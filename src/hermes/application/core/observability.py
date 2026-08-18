import gzip
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_RESPONSE_RETENTION_DAYS = int(os.getenv("GEMINI_RAW_RESPONSE_RETENTION_DAYS", "30") or 30)
RAW_RESPONSE_MAX_MB = int(os.getenv("GEMINI_RAW_RESPONSE_MAX_MB", "50") or 50)
SUSPICIOUS_AUDIT_LOG = REPO_ROOT / "reports" / "suspicious_instruction_audit.jsonl"


def _now() -> datetime:
    return datetime.now()


def cleanup_raw_response_logs(root: str | Path | None = None, retention_days: int | None = None, max_mb: int | None = None) -> dict:
    """Delete old Gemini raw response logs and cap total retained raw-log size."""
    root_path = Path(root or REPO_ROOT)
    retention_days = RAW_RESPONSE_RETENTION_DAYS if retention_days is None else retention_days
    max_bytes = (RAW_RESPONSE_MAX_MB if max_mb is None else max_mb) * 1024 * 1024
    cutoff = _now() - timedelta(days=retention_days)
    candidates = []
    deleted = 0
    compressed = 0

    for path in root_path.rglob("gemini_raw_response*.txt"):
        if not path.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            size = path.stat().st_size
        except OSError:
            continue
        if mtime < cutoff:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                pass
            continue
        candidates.append((mtime, size, path))

    total = sum(size for _, size, _ in candidates)
    if total > max_bytes:
        for _, size, path in sorted(candidates, key=lambda item: item[0]):
            if total <= max_bytes:
                break
            gz_path = path.with_suffix(path.suffix + ".gz")
            try:
                with path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                    dst.write(src.read())
                total -= size
                path.unlink()
                compressed += 1
            except OSError:
                pass

    return {"deleted": deleted, "compressed": compressed}


def write_gemini_raw_response(output_dir: str | Path, raw_text: str, job_id: str = "") -> Path:
    """Write raw Gemini output with timestamped retention, plus a latest pointer file."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stamp = _now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{job_id}" if job_id else ""
    stamped_path = output_path / f"gemini_raw_response{suffix}_{stamp}.txt"
    stamped_path.write_text(raw_text or "", encoding="utf-8")
    latest_path = output_path / "gemini_raw_response.txt"
    latest_path.write_text(raw_text or "", encoding="utf-8")
    cleanup_raw_response_logs()
    return stamped_path


def record_suspicious_instruction(job_id: str, context: str, field: str, pattern: str, text: str) -> None:
    SUSPICIOUS_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    snippet = (text or "").replace("\r", " ").replace("\n", " ")[:500]
    entry = {
        "timestamp": _now().isoformat(timespec="seconds"),
        "job_id": job_id or "",
        "context": context,
        "field": field,
        "pattern": pattern,
        "snippet": snippet,
    }
    with SUSPICIOUS_AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def send_telegram_alert(message: str) -> bool:
    """Send an operational alert to the configured Telegram review/admin chat."""
    enabled = os.getenv("HERMES_ALERTS_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip("'\"")
    chat_id = (
        os.getenv("TELEGRAM_REVIEW_CHAT_ID", "")
        or os.getenv("TELEGRAM_CHAT_ID", "")
    ).strip().strip("'\"")
    if not token or not chat_id:
        return False

    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as response:
            return 200 <= response.status < 300
    except Exception:
        return False
