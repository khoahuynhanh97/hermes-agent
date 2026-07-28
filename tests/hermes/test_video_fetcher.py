from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from core import video_fetcher


class VideoFetcherTests(unittest.TestCase):
    def setUp(self) -> None:
        video_fetcher._reset_transcriber_cache()

    def tearDown(self) -> None:
        video_fetcher._reset_transcriber_cache()

    def test_yt_dlp_commands_use_the_running_interpreter(self) -> None:
        with patch.object(video_fetcher.config, "YTDLP_IMPERSONATE_TARGET", ""):
            command = video_fetcher._yt_dlp_command("--version")

        self.assertEqual(command[:3], [sys.executable, "-m", "yt_dlp"])

    def test_yt_dlp_commands_use_configured_browser_impersonation(self) -> None:
        with patch.object(
            video_fetcher.config,
            "YTDLP_IMPERSONATE_TARGET",
            "Chrome-131:Android-14",
            create=True,
        ):
            command = video_fetcher._yt_dlp_command("--version")

        self.assertEqual(command[:3], [sys.executable, "-m", "yt_dlp"])
        self.assertEqual(command[3:5], ["--impersonate", "Chrome-131:Android-14"])

    def test_audio_command_uses_configured_ffmpeg_location(self) -> None:
        with patch.object(video_fetcher.config, "FFMPEG_PATH", r"C:\\tools\\ffmpeg.exe"):
            command = video_fetcher._audio_download_command(
                "https://example.com/video", Path("output")
            )

        location = command.index("--ffmpeg-location")
        self.assertEqual(command[location + 1], r"C:\\tools\\ffmpeg.exe")
        self.assertEqual(command[:3], [sys.executable, "-m", "yt_dlp"])

    def test_audio_command_uses_imageio_ffmpeg_when_not_configured(self) -> None:
        fake_imageio_ffmpeg = types.SimpleNamespace(get_ffmpeg_exe=lambda: "/managed/ffmpeg")
        with (
            patch.object(video_fetcher.config, "FFMPEG_PATH", ""),
            patch.dict(sys.modules, {"imageio_ffmpeg": fake_imageio_ffmpeg}),
        ):
            command = video_fetcher._audio_download_command(
                "https://example.com/video", Path("output")
            )

        location = command.index("--ffmpeg-location")
        self.assertEqual(command[location + 1], "/managed/ffmpeg")

    def test_tiktok_audio_prefers_download_format_with_audio(self) -> None:
        with (
            patch.object(video_fetcher.config, "FFMPEG_PATH", r"C:\\tools\\ffmpeg.exe"),
            patch.object(video_fetcher.config, "YTDLP_IMPERSONATE_TARGET", ""),
        ):
            command = video_fetcher._audio_download_command(
                "https://vt.tiktok.com/example", Path("output")
            )

        format_index = command.index("-f")
        self.assertEqual(command[format_index + 1], "download/best[acodec!=none]/best")

    def test_transcriber_is_lazy_cached_and_returns_detected_language(self) -> None:
        constructed = []

        class FakeWhisperModel:
            def __init__(self, model, **kwargs):
                constructed.append((model, kwargs))

            def transcribe(self, audio_path):
                return [types.SimpleNamespace(text=" Xin chao ")], types.SimpleNamespace(language="vi")

        fake_backend = types.SimpleNamespace(WhisperModel=FakeWhisperModel)
        with (
            patch.dict(sys.modules, {"faster_whisper": fake_backend}),
            patch.object(video_fetcher.config, "WHISPER_MODEL", "base"),
            patch.object(video_fetcher.config, "WHISPER_DEVICE", "cpu"),
            patch.object(video_fetcher.config, "WHISPER_COMPUTE_TYPE", "int8"),
            patch.object(video_fetcher.config, "WHISPER_MODEL_DIR", "/models"),
        ):
            transcript, language = video_fetcher._transcribe_audio("input.mp3")
            video_fetcher._transcribe_audio("another.mp3")

        self.assertEqual((transcript, language), ("Xin chao", "vi"))
        self.assertEqual(
            constructed,
            [("base", {"device": "cpu", "compute_type": "int8", "download_root": "/models"})],
        )

    def test_missing_stt_backend_returns_clear_needs_source_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mp3"
            source.write_bytes(b"audio")
            with patch.object(
                video_fetcher,
                "_get_transcriber",
                side_effect=video_fetcher.TranscriptionBackendUnavailable("faster-whisper backend unavailable"),
            ), patch.object(video_fetcher, "logger"):
                result = video_fetcher.fetch_transcript(str(source), temp_dir)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["confidence"], "needs_source")
        self.assertIn("faster-whisper backend unavailable", result["error"])

    def test_missing_stt_backend_keeps_url_metadata_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            completed = types.SimpleNamespace(returncode=0, stdout="", stderr="")
            calls = 0

            def run_yt_dlp(*_args, **_kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    (output_dir / "temp_audio.mp3").write_bytes(b"audio")
                return completed

            with (
                patch.object(video_fetcher.subprocess, "run", side_effect=run_yt_dlp),
                patch.object(
                    video_fetcher,
                    "_get_transcriber",
                    side_effect=video_fetcher.TranscriptionBackendUnavailable("faster-whisper backend unavailable"),
                ),
                patch.object(video_fetcher, "_fetch_metadata", return_value={"title": "Video"}),
                patch.object(video_fetcher, "logger"),
            ):
                result = video_fetcher.fetch_transcript("https://example.com/video", temp_dir)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["method"], "metadata")
        self.assertEqual(result["metadata"], {"title": "Video"})
        self.assertEqual(result["confidence"], "low")
        self.assertIn("faster-whisper backend unavailable", result["error"])


if __name__ == "__main__":
    unittest.main()
