"""Tests for Hermes video MVP file contracts."""

from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.video_mvp_contracts import (
    build_remotion_input,
    ensure_video_mvp_paths,
    normalize_product_brief,
    write_json,
)


def run_tests():
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "demo-product"
        paths = ensure_video_mvp_paths(root)
        assert paths.research_dir.exists()
        assert paths.assets_dir.exists()
        assert paths.comfyui_import_dir.exists()
        assert paths.render_dir.exists()
        assert paths.exports_dir.exists()

        brief = normalize_product_brief(
            {"title": "Mini Blender", "description": "Portable blender for smoothies."},
            source_url="https://example.com/blender",
            warnings=["crawl used fallback parser"],
        )
        assert brief["title"] == "Mini Blender"
        assert brief["source_url"] == "https://example.com/blender"
        assert brief["warnings"] == ["crawl used fallback parser"]
        assert "Portable blender" in brief["description"]

        saved = write_json(paths.product_brief_json, brief)
        assert json.loads(saved.read_text(encoding="utf-8"))["title"] == "Mini Blender"

        remotion_input = build_remotion_input(
            project_root=root,
            product_brief=brief,
            hook_text="Blend anywhere",
            voiceover_text="This mini blender helps you make smoothies anywhere.",
            scenes=[{"id": "scene-1", "caption": "Portable size", "asset_path": ""}],
            asset_paths=[],
            duration_seconds=18,
            fps=30,
            cta_text="Check it today",
        )
        assert remotion_input["width"] == 1080
        assert remotion_input["height"] == 1920
        assert remotion_input["fps"] == 30
        assert remotion_input["duration_seconds"] == 18
        assert remotion_input["product"]["title"] == "Mini Blender"
        assert remotion_input["scenes"][0]["caption"] == "Portable size"
    print("video mvp contract tests: PASS")


if __name__ == "__main__":
    run_tests()
