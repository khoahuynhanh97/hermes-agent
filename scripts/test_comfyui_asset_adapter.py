"""Tests for ComfyUI prompt pack adapter."""

from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.comfyui_asset_adapter import (
    build_comfyui_prompt_pack,
    list_comfyui_assets,
    write_comfyui_prompt_pack,
)
from core.video_mvp_contracts import ensure_video_mvp_paths


def run_tests():
    product = {"title": "Mini Blender", "description": "Portable smoothie blender"}
    scenes = [{"id": "hook", "caption": "Blend anywhere"}]
    pack = build_comfyui_prompt_pack(product, scenes)
    assert pack["product_title"] == "Mini Blender"
    assert "vertical 9:16" in pack["prompts"][0]["prompt"]

    with TemporaryDirectory() as tmp:
        paths = ensure_video_mvp_paths(Path(tmp) / "project")
        saved = write_comfyui_prompt_pack(paths, product, scenes)
        assert json.loads(saved.read_text(encoding="utf-8"))["prompts"][0]["scene_id"] == "hook"
        image = paths.comfyui_import_dir / "asset.png"
        image.write_text("fake", encoding="utf-8")
        assert list_comfyui_assets(paths) == [str(image)]
    print("comfyui asset adapter tests: PASS")


if __name__ == "__main__":
    run_tests()
