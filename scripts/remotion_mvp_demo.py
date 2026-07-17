"""Standalone Remotion MVP demo command."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.comfyui_asset_adapter import list_comfyui_assets, write_comfyui_prompt_pack
from core.remotion_renderer import render_with_remotion, write_remotion_input
from core.video_mvp_contracts import build_remotion_input, ensure_video_mvp_paths, normalize_product_brief, write_json
from editor.ffmpeg_finalizer import finalize_video


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and optionally render a Hermes Remotion MVP demo project")
    parser.add_argument("--project-root", default="projects", help="Projects root directory")
    parser.add_argument("--project", default="remotion-demo", help="Demo project folder name")
    parser.add_argument("--skip-render", action="store_true", help="Only write contracts and JSON files")
    return parser.parse_args()


def run_remotion_demo(project_root: Path, project_name: str, skip_render: bool = False) -> dict:
    project_dir = Path(project_root) / project_name
    paths = ensure_video_mvp_paths(project_dir)
    product = normalize_product_brief(
        {
            "title": "Hermes Demo Product",
            "description": "A compact product review demo for validating the Remotion MVP pipeline.",
            "selling_points": ["Clear hook", "Readable captions", "Fast vertical render"],
        },
        warnings=["demo data"],
    )
    scenes = [
        {"id": "scene-1", "caption": "Show the product clearly in the first seconds"},
        {"id": "scene-2", "caption": "Explain the main benefit with one simple sentence"},
        {"id": "scene-3", "caption": "Close with a direct call to action"},
    ]
    write_json(paths.product_brief_json, product)
    paths.product_brief_md.write_text(
        f"# {product['title']}\n\n{product['description']}\n",
        encoding="utf-8",
    )
    write_comfyui_prompt_pack(paths, product, scenes)
    remotion_payload = build_remotion_input(
        project_root=project_dir,
        product_brief=product,
        hook_text="Stop scrolling for this product",
        voiceover_text="This demo validates the Hermes Remotion MVP pipeline.",
        scenes=scenes,
        asset_paths=list_comfyui_assets(paths),
        duration_seconds=24,
        fps=30,
        cta_text="Save this product idea",
    )
    write_remotion_input(paths, remotion_payload)
    remotion_status = {"ok": False, "reason": "skipped"}
    final_status = {"ok": False, "reason": "skipped"}
    if not skip_render:
        remotion_status = render_with_remotion(paths)
        if remotion_status.get("ok"):
            final_status = finalize_video(paths.remotion_final_mp4, paths.final_mp4)
        else:
            final_status = finalize_video(paths.remotion_final_mp4, paths.final_mp4)
    return {
        "project": str(project_dir),
        "remotion_input": str(paths.remotion_input_json),
        "comfyui_prompts": str(paths.comfyui_prompts_json),
        "remotion": remotion_status,
        "final": final_status,
    }


def main() -> int:
    args = parse_args()
    result = run_remotion_demo(Path(args.project_root), args.project, skip_render=args.skip_render)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["remotion"].get("ok") or args.skip_render else 1


if __name__ == "__main__":
    raise SystemExit(main())
