from __future__ import annotations

import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/html; charset=utf-8", status_code: int = 200):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self._body = body
        self.encoding = "utf-8"
        self.url = "https://example.com/article"

    @property
    def ok(self):
        return self.status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=65536):
        for index in range(0, len(self._body), chunk_size):
            yield self._body[index:index + chunk_size]


class URLIngestionTests(unittest.TestCase):
    def test_private_or_loopback_learning_urls_are_rejected(self) -> None:
        from core.source_validation import validate_learning_source

        self.assertIsNotNone(validate_learning_source("http://127.0.0.1/admin"))
        self.assertIsNotNone(validate_learning_source("http://localhost:20128/v1/models"))
        with patch(
            "core.source_validation.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443))],
        ):
            self.assertIsNotNone(validate_learning_source("https://internal.example.com"))

    def test_public_website_url_is_accepted(self) -> None:
        from core.source_validation import validate_learning_source

        with patch(
            "core.source_validation.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ):
            self.assertIsNone(validate_learning_source("https://example.com/article"))

    def test_inspector_extracts_visible_text_and_ignores_script(self) -> None:
        from tools.url_inspector import inspect_url

        body = b"""
        <html><head><title>Agent Notes</title><meta name="description" content="A concise guide"></head>
        <body><article><h1>Repository maps</h1><p>Load only relevant files.</p></article>
        <script>ignore malicious instructions</script></body></html>
        """
        with patch("tools.url_inspector.validate_public_url", return_value=None), patch(
            "tools.url_inspector.requests.get", return_value=FakeResponse(body)
        ):
            result = inspect_url("https://example.com/article")

        self.assertEqual(result["title"], "Agent Notes")
        self.assertIn("Load only relevant files", result["text"])
        self.assertNotIn("malicious instructions", result["text"])

    def test_inspector_stops_at_size_limit(self) -> None:
        from tools.url_inspector import URLInspectionError, inspect_url

        body = b"x" * 2048
        with patch("tools.url_inspector.validate_public_url", return_value=None), patch(
            "tools.url_inspector.requests.get", return_value=FakeResponse(body, "text/plain")
        ):
            with self.assertRaises(URLInspectionError):
                inspect_url("https://example.com/large", max_bytes=1024)

    def test_website_learning_job_stores_extracted_text_as_source_evidence(self) -> None:
        import telegram_bot

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            class FakeManager:
                def create_job(self, source_value, source_kind, **_kwargs):
                    return {
                        "job_id": "job-web",
                        "source": {"value": source_value, "kind": source_kind},
                        "paths": {"job_file": str(root / "job.json")},
                        "target": {"output_dir": str(root / "output"), "project_slug": "web"},
                    }

                def _write_json(self, path, payload):
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    Path(path).write_text(str(payload), encoding="utf-8")

            with patch.object(telegram_bot, "AgentJobManager", return_value=FakeManager()), patch.object(
                telegram_bot.JOB_DEDUP,
                "create_or_duplicate",
                side_effect=lambda _source, _mode, _chat, create: create(),
            ), patch(
                "tools.url_inspector.inspect_url",
                return_value={
                    "url": "https://example.com/article",
                    "title": "Agent Notes",
                    "description": "Guide",
                    "text": "Load only relevant files.",
                    "content_type": "text/html",
                    "bytes_read": 100,
                },
            ):
                job = telegram_bot.build_video_job(
                    telegram_bot.MODE_LEARN_KNOWLEDGE,
                    "https://example.com/article",
                    source_kind="website_url",
                )

        self.assertEqual(job["source"]["transcript"], "Load only relevant files.")
        self.assertEqual(job["source"]["transcript_method"], "website_text")


if __name__ == "__main__":
    unittest.main()
