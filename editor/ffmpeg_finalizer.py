from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess


def resolve_ffmpeg_path(ffmpeg_path: str = "") -> str:
    if ffmpeg_path:
        return ffmpeg_path
    try:
        config = importlib.import_module("config")
        configured = getattr(config, "FFMPEG_PATH", "")
        if configured and os.path.exists(configured):
            return configured
    except Exception:
        pass
    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def build_ffmpeg_normalize_command(input_path: str | Path, output_path: str | Path, ffmpeg_path: str = "") -> list[str]:
    ffmpeg = resolve_ffmpeg_path(ffmpeg_path)
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1"
    return [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def finalize_video(
    input_path: str | Path,
    output_path: str | Path,
    ffmpeg_path: str = "",
    timeout_seconds: int = 300,
) -> dict:
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        return {"ok": False, "reason": "input_missing", "input": str(src)}
    dst.parent.mkdir(parents=True, exist_ok=True)
    command = build_ffmpeg_normalize_command(src, dst, ffmpeg_path=ffmpeg_path)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except Exception as exc:
        return {"ok": False, "reason": "subprocess_error", "error": str(exc), "command": command}
    return {
        "ok": completed.returncode == 0,
        "reason": "finalized" if completed.returncode == 0 else "ffmpeg_failed",
        "returncode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
        "command": command,
        "output": str(dst),
    }
