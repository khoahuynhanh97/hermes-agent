"""AIGC watermark & metadata embedding for video outputs."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes.adapters.local.ffmpeg_capability import resolve_ffmpeg_exe


class AIGCWatermarkEmbedder:
    """Embeds AIGC disclosure metadata into video files."""

    def __init__(self, ffmpeg_path: str | None = None):
        self.ffmpeg_path = ffmpeg_path or resolve_ffmpeg_exe()

    def embed_metadata(
        self,
        video_path: str,
        project_id: str,
        variant_id: str = "",
        tool_name: str = "hermes-agent",
    ) -> dict[str, Any]:
        """Embed AIGC metadata using FFmpeg.

        Adds creation_time, software, comment, and custom aigc_* tags.

        Returns:
            {"success": bool, "output_path": str}
        """
        src = Path(video_path)
        if not src.is_file():
            return {"success": False, "output_path": "", "error": "input not found"}

        out = src.with_name(f"{src.stem}_aigc{src.suffix}")
        timestamp = datetime.now(timezone.utc).isoformat()

        cmd = [
            self.ffmpeg_path, "-y",
            "-i", str(src),
            "-metadata:s:v:0", f"comment=AI-generated content",
            "-metadata", f"comment=Created by {tool_name}",
            "-metadata", f"software={tool_name}",
            "-metadata:s:v:0", f"handler_name={tool_name}",
            "-metadata", f"creation_time={timestamp}",
            "-metadata", f"aigc_tool={tool_name}",
            "-metadata", f"aigc_project={project_id}",
            "-metadata", f"aigc_variant={variant_id}",
            "-c", "copy",
            str(out),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0 and out.is_file() and out.stat().st_size > 0:
                return {"success": True, "output_path": str(out)}
        except Exception:
            pass

        return {"success": False, "output_path": "", "error": "FFmpeg metadata embed failed"}

    def embed_c2pa_sidecar(
        self, video_path: str, project_id: str
    ) -> dict[str, Any]:
        """Create C2PA-compatible sidecar JSON manifest.

        Full C2PA SDK integration is future work — this creates the manifest structure.
        """
        src = Path(video_path)
        manifest = {
            "claim_generator": "hermes-agent",
            "instance_id": f"urn:hermes:{project_id}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "asset": {
                "file_name": src.name,
                "mime_type": "video/mp4",
            },
            "assertions": [
                {
                    "label": "c2pa.hash.data",
                    "data": {"name": "AIGC-generated content"},
                },
                {
                    "label": "c2pa provenance",
                    "data": {
                        "tool": "hermes-agent",
                        "project_id": project_id,
                    },
                },
            ],
            "signature": {
                "algorithm": "placeholder",
                "note": "C2PA cryptographic signing requires SDK integration",
            },
        }

        sidecar_path = src.with_suffix(".c2pa.json")
        try:
            sidecar_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            return {"success": True, "sidecar_path": str(sidecar_path)}
        except Exception:
            return {"success": False, "sidecar_path": "", "error": "Failed to write sidecar manifest"}
