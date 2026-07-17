"""Tests for Remotion MVP demo command wiring."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

import scripts.remotion_mvp_demo as remotion_mvp_demo


def run_tests():
    with TemporaryDirectory() as tmp:
        with patch.object(sys, "argv", ["remotion_mvp_demo.py", "--project-root", tmp, "--project", "demo"]):
            args = remotion_mvp_demo.parse_args()
        assert args.project == "demo"

        with (
            patch("scripts.remotion_mvp_demo.render_with_remotion", return_value={"ok": False, "reason": "renderer_dir_missing"}),
            patch("scripts.remotion_mvp_demo.finalize_video", return_value={"ok": False, "reason": "input_missing"}),
        ):
            result = remotion_mvp_demo.run_remotion_demo(Path(tmp), "demo", skip_render=False)
        assert result["project"].endswith("demo")
        assert result["remotion"]["ok"] is False
        assert (Path(tmp) / "demo" / "render" / "remotion_input.json").exists()
    print("remotion demo command tests: PASS")


if __name__ == "__main__":
    run_tests()
