from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VideoMvpPaths:
    project_root: Path
    research_dir: Path
    assets_dir: Path
    comfyui_import_dir: Path
    render_dir: Path
    exports_dir: Path
    product_brief_json: Path
    product_brief_md: Path
    comfyui_prompts_json: Path
    remotion_input_json: Path
    remotion_status_json: Path
    remotion_final_mp4: Path
    final_mp4: Path


def ensure_video_mvp_paths(project_root: str | Path) -> VideoMvpPaths:
    root = Path(project_root)
    research_dir = root / "research"
    assets_dir = root / "assets"
    comfyui_import_dir = assets_dir / "comfyui_import"
    render_dir = root / "render"
    exports_dir = root / "exports"
    for path in [research_dir, assets_dir, comfyui_import_dir, render_dir, exports_dir]:
        path.mkdir(parents=True, exist_ok=True)
    return VideoMvpPaths(
        project_root=root,
        research_dir=research_dir,
        assets_dir=assets_dir,
        comfyui_import_dir=comfyui_import_dir,
        render_dir=render_dir,
        exports_dir=exports_dir,
        product_brief_json=research_dir / "product_brief.json",
        product_brief_md=research_dir / "product_brief.md",
        comfyui_prompts_json=assets_dir / "comfyui_prompts.json",
        remotion_input_json=render_dir / "remotion_input.json",
        remotion_status_json=render_dir / "remotion_status.json",
        remotion_final_mp4=exports_dir / "remotion_final.mp4",
        final_mp4=exports_dir / "final.mp4",
    )


def normalize_product_brief(
    raw: dict[str, Any],
    source_url: str = "",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    selling_points = raw.get("selling_points") or raw.get("benefits") or []
    if isinstance(selling_points, str):
        selling_points = [line.strip() for line in selling_points.splitlines() if line.strip()]
    return {
        "title": str(raw.get("title") or raw.get("name") or "Untitled product").strip(),
        "description": str(raw.get("description") or raw.get("summary") or "").strip(),
        "selling_points": list(selling_points),
        "target_customer": str(raw.get("target_customer") or raw.get("audience") or "").strip(),
        "pain_points": list(raw.get("pain_points") or []),
        "claims": list(raw.get("claims") or []),
        "objections": list(raw.get("objections") or []),
        "source_url": source_url or str(raw.get("source_url") or "").strip(),
        "warnings": list(warnings or raw.get("warnings") or []),
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def build_remotion_input(
    project_root: str | Path,
    product_brief: dict[str, Any],
    hook_text: str,
    voiceover_text: str,
    scenes: list[dict[str, Any]],
    asset_paths: list[str],
    duration_seconds: int = 24,
    fps: int = 30,
    cta_text: str = "",
) -> dict[str, Any]:
    return {
        "project_root": str(Path(project_root).resolve()),
        "width": 1080,
        "height": 1920,
        "fps": int(fps),
        "duration_seconds": int(duration_seconds),
        "product": product_brief,
        "hook_text": hook_text.strip(),
        "voiceover_text": voiceover_text.strip(),
        "scenes": scenes,
        "asset_paths": asset_paths,
        "cta_text": cta_text.strip(),
    }
