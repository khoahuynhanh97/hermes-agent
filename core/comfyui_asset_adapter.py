from __future__ import annotations

from pathlib import Path
from typing import Any

from core.video_mvp_contracts import VideoMvpPaths, write_json


ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}


def build_comfyui_prompt_pack(product_brief: dict[str, Any], scenes: list[dict[str, Any]]) -> dict[str, Any]:
    title = product_brief.get("title", "Product")
    description = product_brief.get("description", "")
    prompts = []
    for index, scene in enumerate(scenes or [{"id": "hero", "caption": "Hero product shot"}], start=1):
        caption = scene.get("caption") or scene.get("text") or "Product benefit"
        prompts.append(
            {
                "scene_id": scene.get("id", f"scene-{index}"),
                "prompt": (
                    f"vertical 9:16 TikTok product review scene, {title}, {caption}, "
                    f"realistic commercial lighting, clean background, high detail. Product context: {description}"
                ),
            }
        )
    return {"product_title": title, "source": "hermes", "prompts": prompts}


def write_comfyui_prompt_pack(
    paths: VideoMvpPaths,
    product_brief: dict[str, Any],
    scenes: list[dict[str, Any]],
) -> Path:
    return write_json(paths.comfyui_prompts_json, build_comfyui_prompt_pack(product_brief, scenes))


def list_comfyui_assets(paths: VideoMvpPaths) -> list[str]:
    if not paths.comfyui_import_dir.exists():
        return []
    files = [
        item
        for item in paths.comfyui_import_dir.iterdir()
        if item.is_file() and item.suffix.lower() in ASSET_EXTENSIONS
    ]
    return [str(item) for item in sorted(files)]
