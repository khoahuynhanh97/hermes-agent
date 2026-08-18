"""Focused checks for image-carousel analysis input validation."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from hermes.tools import video_analyser


def run_missing_vision_configuration_check() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        slide = Path(temp_dir) / "slide.jpg"
        slide.write_bytes(b"image")
        with patch.object(video_analyser, "init_gemini", return_value=False):
            try:
                video_analyser.analyze_images([slide], "Analyze the slides")
            except RuntimeError as exc:
                assert "vision" in str(exc).lower()
            else:
                raise AssertionError("image analysis must fail transparently without a vision model")


def run_tests() -> None:
    run_missing_vision_configuration_check()
    print("image analyser checks: PASS")


if __name__ == "__main__":
    run_tests()
