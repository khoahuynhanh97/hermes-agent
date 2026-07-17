"""Tests for FFmpeg finalization command builder."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from editor.ffmpeg_finalizer import build_ffmpeg_normalize_command, finalize_video


def run_tests():
    cmd = build_ffmpeg_normalize_command("in.mp4", "out.mp4", ffmpeg_path="ffmpeg")
    assert cmd[:4] == ["ffmpeg", "-y", "-i", "in.mp4"]
    assert "scale=1080:1920:force_original_aspect_ratio=decrease" in " ".join(cmd)
    assert cmd[-1] == "out.mp4"

    with TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        dst = Path(tmp) / "out.mp4"
        missing = finalize_video(src, dst, ffmpeg_path="ffmpeg")
        assert missing["ok"] is False
        assert missing["reason"] == "input_missing"

        src.write_text("fake", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        with patch("editor.ffmpeg_finalizer.subprocess.run", return_value=Completed()) as mocked:
            result = finalize_video(src, dst, ffmpeg_path="ffmpeg", timeout_seconds=5)
        assert result["ok"] is True
        assert mocked.call_args.args[0][0] == "ffmpeg"
    print("ffmpeg finalizer tests: PASS")


if __name__ == "__main__":
    run_tests()
