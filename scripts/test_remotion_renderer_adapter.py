"""Tests for Remotion subprocess adapter."""

from pathlib import Path
import json
import os
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.remotion_renderer import render_with_remotion, write_remotion_input
from core.video_mvp_contracts import ensure_video_mvp_paths


def run_tests():
    with TemporaryDirectory() as tmp:
        paths = ensure_video_mvp_paths(Path(tmp) / "project")
        payload = {"width": 1080, "height": 1920, "fps": 30, "duration_seconds": 10}
        saved = write_remotion_input(paths, payload)
        assert json.loads(saved.read_text(encoding="utf-8"))["width"] == 1080

        missing = render_with_remotion(paths, renderer_dir=Path(tmp) / "missing")
        assert missing["ok"] is False
        assert missing["reason"] == "renderer_dir_missing"
        assert paths.remotion_status_json.exists()

        renderer = Path(tmp) / "renderer"
        renderer.mkdir()
        (renderer / "render.mjs").write_text("", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "rendered"
            stderr = ""

        with patch("core.remotion_renderer.subprocess.run", return_value=Completed()) as mocked:
            result = render_with_remotion(paths, renderer_dir=renderer, node_executable="node", timeout_seconds=5)
        assert result["ok"] is True
        assert mocked.call_args.args[0][0] == "node"
        assert str(paths.remotion_input_json) in mocked.call_args.args[0]

    original_cwd = Path.cwd()
    with TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            paths = ensure_video_mvp_paths(Path(tmp) / "project")
            write_remotion_input(paths, {"width": 1080})
            relative_renderer = Path("renderer")
            relative_renderer.mkdir()
            (relative_renderer / "render.mjs").write_text("", encoding="utf-8")

            class Completed:
                returncode = 0
                stdout = "rendered"
                stderr = ""

            with patch("core.remotion_renderer.subprocess.run", return_value=Completed()) as mocked:
                result = render_with_remotion(paths, renderer_dir=relative_renderer, node_executable="node")
            assert result["ok"] is True
            assert Path(mocked.call_args.args[0][1]).is_absolute()
        finally:
            os.chdir(original_cwd)
    print("remotion renderer adapter tests: PASS")


if __name__ == "__main__":
    run_tests()
