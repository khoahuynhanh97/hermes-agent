from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class MediaAnalysisContractTests(unittest.TestCase):
    def test_learning_analysis_raises_when_vision_provider_is_unavailable(self) -> None:
        from tools.video_analyser import MediaAnalysisUnavailable, analyze_video

        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "source.mp4"
            video_path.write_bytes(b"not-a-real-video")

            with patch("tools.video_analyser.init_gemini", return_value=False):
                with self.assertRaises(MediaAnalysisUnavailable):
                    analyze_video(str(video_path), prompt_text="Analyze only real source evidence")

    def test_explicit_offline_inspection_remains_available(self) -> None:
        from tools.video_analyser import analyze_video

        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "source.mp4"
            video_path.write_bytes(b"not-a-real-video")

            result = analyze_video(str(video_path), offline_only=True)

        self.assertIsInstance(result, str)
        self.assertTrue(result.strip())

    def test_offline_inspection_does_not_crash_on_cp1252_console(self) -> None:
        from tools.video_analyser import analyze_video

        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "source.mp4"
            video_path.write_bytes(b"not-a-real-video")
            output = io.BytesIO()
            console = io.TextIOWrapper(output, encoding="cp1252", errors="strict")

            with patch("sys.stdout", console):
                result = analyze_video(str(video_path), offline_only=True)

            console.detach()

        self.assertTrue(result.strip())

    def test_video_analysis_uses_google_genai_client(self) -> None:
        from tools.video_analyser import analyze_video

        class UploadedFile:
            name = "files/test-video"
            state = "ACTIVE"

        class Files:
            def __init__(self):
                self.deleted = []

            def upload(self, *, file):
                self.uploaded = file
                return UploadedFile()

            def get(self, *, name):
                return UploadedFile()

            def delete(self, *, name):
                self.deleted.append(name)

        class Models:
            def generate_content(self, *, model, contents):
                self.model = model
                self.contents = contents
                return type("Response", (), {"text": "source-bound analysis"})()

        client = type("Client", (), {"files": Files(), "models": Models()})()
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "source.mp4"
            video_path.write_bytes(b"video")
            with (
                patch("tools.video_analyser.init_gemini", return_value=True),
                patch("tools.video_analyser.get_gemini_client", return_value=client),
            ):
                result = analyze_video(str(video_path), prompt_text="Analyze")

        self.assertEqual(result, "source-bound analysis")
        self.assertEqual(client.files.deleted, ["files/test-video"])
        self.assertIn("gemini", client.models.model)


if __name__ == "__main__":
    unittest.main()
