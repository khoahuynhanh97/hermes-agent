"""Thin Video MCP facade over existing video services and job persistence."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.application.video_service import VideoService
from hermes.config import get_data_path
from hermes.domain.job import JobStatus
from tools.video_analyser import analyze_video


mcp = FastMCP("hermes-video")
SUPPORTED_FORMATS = {"mp4", "mov", "webm"}


def video_create_job(
    owner_user_id: str,
    operation: str,
    asset_path: str,
    output_name: str = "",
    start_seconds: int = 0,
    end_seconds: int = 60,
    output_format: str = "mp4",
) -> dict[str, Any]:
    """Enqueue a bounded cut/render operation; media execution remains durable."""
    owner_user_id = _required(owner_user_id, "owner_user_id")
    operation = _required(operation, "operation").lower()
    input_path = _resolve_asset(asset_path)
    output_path = _resolve_output(output_name, output_format)
    if operation == "cut":
        if not isinstance(start_seconds, int) or not isinstance(end_seconds, int):
            raise ValueError("start_seconds and end_seconds must be integers")
        if start_seconds < 0 or end_seconds <= start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds >= 0")
        result = _video_service().request_cut(
            str(input_path),
            start_seconds,
            end_seconds,
            owner_user_id=owner_user_id,
            output_path=str(output_path),
        )
    elif operation == "render":
        output_format = _validate_format(output_format)
        result = _video_service().request_render(
            str(input_path),
            output_format,
            owner_user_id=owner_user_id,
            output_path=str(output_path),
        )
    else:
        raise ValueError("operation must be 'cut' or 'render'")
    if not result.ok:
        raise ValueError(result.message)
    return {"ok": True, "execution_mode": "durable_job", "job": _job_payload(result.value)}


def video_get_job(owner_user_id: str, job_id: str) -> dict[str, Any]:
    """Read structured status for one owner-scoped video job."""
    owner_user_id = _required(owner_user_id, "owner_user_id")
    job_id = _required(job_id, "job_id")
    job = _repository().get_job(job_id)
    if job is None:
        raise ValueError("JOB_NOT_FOUND")
    if str(job.payload.get("owner_user_id") or "") != owner_user_id:
        raise ValueError("OWNER_MISMATCH")
    return {"ok": True, "job": _job_payload(job)}


def video_analyze(owner_user_id: str, asset_path: str, custom_action: str = "") -> dict[str, Any]:
    """Run the existing offline media inspection without paid provider calls."""
    owner_user_id = _required(owner_user_id, "owner_user_id")
    input_path = _resolve_asset(asset_path)
    analysis = analyze_video(
        str(input_path),
        custom_action=custom_action or None,
        offline_only=True,
    )
    return {
        "ok": True,
        "owner_user_id": owner_user_id,
        "asset_path": str(input_path),
        "mode": "offline_inspection",
        "analysis": analysis,
        "rights_status": "reference_only",
    }


def _video_service() -> VideoService:
    return VideoService(_repository())


def _repository() -> CanonicalJobRepository:
    configured = os.environ.get("HERMES_VIDEO_DB_PATH", "").strip()
    path = Path(configured).expanduser().resolve() if configured else get_data_path("db", "video.sqlite")
    return CanonicalJobRepository(str(path))


def _workspace() -> Path:
    configured = os.environ.get("HERMES_VIDEO_WORKSPACE", "").strip()
    root = Path(configured).expanduser().resolve() if configured else get_data_path("workspaces", "video")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_asset(value: str) -> Path:
    candidate = Path(_required(value, "asset_path")).expanduser().resolve()
    _ensure_contained(candidate)
    if not candidate.is_file():
        raise ValueError("ASSET_NOT_FOUND")
    if candidate.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv", ".avi"}:
        raise ValueError("UNSUPPORTED_MEDIA")
    return candidate


def _resolve_output(output_name: str, output_format: str) -> Path:
    output_format = _validate_format(output_format)
    name = (output_name or f"output.{output_format}").strip()
    candidate = (_workspace() / name).resolve()
    _ensure_contained(candidate)
    if candidate.suffix.lower().lstrip(".") not in SUPPORTED_FORMATS:
        raise ValueError("output_name must use a supported media extension")
    return candidate


def _ensure_contained(path: Path) -> None:
    try:
        path.relative_to(_workspace())
    except ValueError as error:
        raise ValueError("UNAUTHORIZED_PATH") from error


def _validate_format(value: str) -> str:
    value = (value or "").strip().lower()
    if value not in SUPPORTED_FORMATS:
        raise ValueError("unsupported output format")
    return value


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _job_payload(job: Any) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "task_name": job.task_name,
        "status": job.status.name.lower(),
        "owner_user_id": job.payload.get("owner_user_id", ""),
        "payload": {
            key: value
            for key, value in job.payload.items()
            if key != "asset_id" or _is_workspace_path(value)
        },
        "result": job.result,
        "error": job.error,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "worker_id": job.worker_id,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _is_workspace_path(value: Any) -> bool:
    try:
        _ensure_contained(Path(str(value)).resolve())
        return True
    except (ValueError, OSError):
        return False


for _tool in (video_create_job, video_get_job, video_analyze):
    mcp.tool()(_tool)


if __name__ == "__main__":
    mcp.run()
