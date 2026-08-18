"""Focused tests for bounded learning-source fallback behavior."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from hermes.application.core.job_watcher import JobWorker
from hermes.application.core.video_fetcher import fetch_transcript
from hermes.tools.tiktok_media_resolver import TikTokMediaResult


class FakeProcess:
    returncode = 0
    stdout = json.dumps({
        "title": "A public tutorial",
        "description": "Short description",
        "uploader": "Example channel",
        "duration": 42,
        "webpage_url": "https://www.youtube.com/watch?v=example",
    })
    stderr = ""


def run_tests():
    with patch("core.video_fetcher.subprocess.run", side_effect=[
        FakeProcess(),  # subtitle attempt
        FakeProcess(),  # subtitle retry
        FakeProcess(),  # audio attempt
        FakeProcess(),  # audio retry
        FakeProcess(),  # metadata fallback
    ]):
        result = fetch_transcript(
            "https://www.youtube.com/watch?v=example",
            str(Path(__file__).resolve().parent / ".tmp_learning_fallback"),
        )

    assert result["status"] == "partial"
    assert result["method"] == "metadata"
    assert result["confidence"] == "low"
    assert result["metadata"]["title"] == "A public tutorial"

    context = JobWorker().prepare_source_metadata_context(result["metadata"])
    assert "LOW-CONFIDENCE" in context
    assert "does not prove" in context
    assert "Short description" in context

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        slide = output_dir / "source_images" / "slide-01.jpg"
        slide.parent.mkdir(parents=True)
        slide.write_bytes(b"image")
        photo_result = TikTokMediaResult(
            source_kind="photo",
            media_paths=[slide],
            metadata={"title": "Photo slides"},
            confidence="high",
        )
        worker = JobWorker()
        with patch("core.job_watcher.resolve_tiktok_media", return_value=photo_result), patch(
            "core.job_watcher.download_video", side_effect=AssertionError("photo must not use yt-dlp")
        ):
            result = worker._resolve_tiktok_source(
                "https://www.tiktok.com/@author/photo/123",
                output_dir,
            )
        assert result is photo_result

        with patch("tools.video_analyser.analyze_images", return_value="Slide evidence analysis") as analyze_images:
            analysis = worker._analyze_tiktok_photo(photo_result, "Analyze the slides")
        assert analysis == "Slide evidence analysis"
        analyze_images.assert_called_once_with([slide], "Analyze the slides")

        job = {"source": {"value": "https://www.tiktok.com/@author/video/123"}}
        fetch_result = {
            "transcript": "Spoken source evidence",
            "method": "caption",
            "metadata": {"title": "Video"},
            "status": "ok",
            "confidence": "medium",
        }
        with patch("core.video_fetcher.fetch_transcript", return_value=fetch_result):
            worker._fetch_deferred_tiktok_context(job, output_dir)
        assert job["source"]["transcript"] == "Spoken source evidence"
        assert job["source"]["transcript_method"] == "caption"

    print("learning fallback tests: PASS")


if __name__ == "__main__":
    run_tests()
