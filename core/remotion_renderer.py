from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from core.video_mvp_contracts import VideoMvpPaths, write_json


def write_remotion_input(paths: VideoMvpPaths, payload: dict[str, Any]) -> Path:
    return write_json(paths.remotion_input_json, payload)


def _write_status(paths: VideoMvpPaths, status: dict[str, Any]) -> dict[str, Any]:
    write_json(paths.remotion_status_json, status)
    return status


def render_with_remotion(
    paths: VideoMvpPaths,
    renderer_dir: str | Path | None = None,
    node_executable: str = "node",
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    renderer = Path(renderer_dir or "remotion_renderer").resolve()
    render_script = renderer / "render.mjs"
    if not renderer.exists():
        return _write_status(paths, {"ok": False, "reason": "renderer_dir_missing", "renderer_dir": str(renderer)})
    if not render_script.exists():
        return _write_status(paths, {"ok": False, "reason": "render_script_missing", "render_script": str(render_script)})
    command = [
        node_executable,
        str(render_script),
        str(paths.remotion_input_json.resolve()),
        str(paths.remotion_final_mp4.resolve()),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(renderer),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return _write_status(paths, {"ok": False, "reason": "subprocess_error", "error": str(exc), "command": command})
    status = {
        "ok": completed.returncode == 0,
        "reason": "rendered" if completed.returncode == 0 else "render_failed",
        "returncode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
        "command": command,
        "output": str(paths.remotion_final_mp4),
    }
    return _write_status(paths, status)
