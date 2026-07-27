from __future__ import annotations

import base64
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import tiktok_media_resolver as resolver


ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "application/json") -> None:
        self._payload = payload
        self._offset = 0
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(payload)),
        }
        self.status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._payload) - self._offset
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def iter_content(self, chunk_size: int):
        while chunk := self.read(chunk_size):
            yield chunk

    def raise_for_status(self) -> None:
        return None

    def close(self) -> None:
        return None


class TikTokCrawlerHealthTests(unittest.TestCase):
    def test_health_is_ready_only_when_required_endpoint_exists(self) -> None:
        payload = json.dumps(
            {"paths": {"/api/hybrid/video_data": {"get": {}}}}
        ).encode("utf-8")
        with patch.object(resolver, "urlopen", return_value=_FakeResponse(payload)):
            health = resolver.check_crawler_health()

        self.assertEqual(health.status, "ready")
        self.assertTrue(health.compatible)

    def test_health_reports_incompatible_openapi_contract(self) -> None:
        payload = json.dumps({"paths": {"/docs": {"get": {}}}}).encode("utf-8")
        with patch.object(resolver, "urlopen", return_value=_FakeResponse(payload)):
            health = resolver.check_crawler_health()

        self.assertEqual(health.status, "incompatible")
        self.assertFalse(health.compatible)

    def test_impersonated_page_rejects_private_redirect(self) -> None:
        response = unittest.mock.MagicMock()
        response.status_code = 302
        response.headers = {"Location": "http://127.0.0.1/private"}
        response.url = "https://www.tiktok.com/redirect"
        fake_requests = types.SimpleNamespace(get=unittest.mock.MagicMock(return_value=response))
        fake_curl = types.SimpleNamespace(requests=fake_requests)
        with (
            patch.dict(sys.modules, {"curl_cffi": fake_curl}),
            patch.object(
                resolver,
                "validate_public_url",
                side_effect=lambda url: "private target" if "127.0.0.1" in url else None,
            ),
        ):
            page = resolver._fetch_impersonated_page(
                "https://www.tiktok.com/@author/photo/123"
            )

        self.assertIsNone(page)
        self.assertEqual(fake_requests.get.call_count, 1)


class TikTokImageDownloadTests(unittest.TestCase):
    def test_download_rejects_private_network_url_before_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "slide.png"
            with patch.object(resolver.requests, "get") as get:
                with self.assertRaises(ValueError):
                    resolver._download_image(
                        "http://127.0.0.1/private.png", destination, max_bytes=1024
                    )

            get.assert_not_called()
            self.assertFalse(destination.exists())

    def test_download_rejects_redirect_to_private_network(self) -> None:
        response = unittest.mock.MagicMock()
        response.status_code = 302
        response.headers = {"Location": "http://127.0.0.1/private.png"}
        response.close.return_value = None
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "slide.png"
            with (
                patch.object(resolver.requests, "get", return_value=response) as get,
                patch.object(
                    resolver,
                    "validate_public_url",
                    side_effect=lambda url: "private target" if "127.0.0.1" in url else None,
                ),
            ):
                with self.assertRaises(ValueError):
                    resolver._download_image(
                        "https://cdn.example/public.png", destination, max_bytes=1024
                    )

            self.assertEqual(get.call_count, 1)
            self.assertFalse(destination.exists())

    def test_download_rejects_non_image_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "slide.jpg"
            response = _FakeResponse(b"<html>blocked</html>", "text/html")
            with (
                patch.object(resolver.requests, "get", return_value=response),
                patch.object(resolver, "validate_public_url", return_value=None),
            ):
                with self.assertRaises(ValueError):
                    resolver._download_image(
                        "https://cdn.example/slide.jpg", destination, max_bytes=1024
                    )

            self.assertFalse(destination.exists())

    def test_download_accepts_and_verifies_real_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "slide.png"
            response = _FakeResponse(ONE_PIXEL_PNG, "image/png")
            with (
                patch.object(resolver.requests, "get", return_value=response),
                patch.object(resolver, "validate_public_url", return_value=None),
            ):
                downloaded = resolver._download_image(
                    "https://cdn.example/slide.png", destination, max_bytes=1024
                )

            self.assertEqual(downloaded, destination)
            self.assertEqual(destination.read_bytes(), ONE_PIXEL_PNG)

    def test_html_metadata_photo_urls_are_used_when_crawler_fails(self) -> None:
        metadata = {
            "resolved_url": "https://www.tiktok.com/@author/photo/123",
            "title": "Photo lesson",
            "image_urls": ["https://cdn.example/one.png"],
        }

        def fake_download(_url: str, destination: Path, **_kwargs) -> Path:
            destination.write_bytes(ONE_PIXEL_PNG)
            return destination

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(resolver, "_call_crawler", side_effect=OSError("offline")),
                patch.object(resolver, "_fetch_public_metadata", return_value=metadata),
                patch.object(resolver, "_download_image", side_effect=fake_download),
            ):
                result = resolver.resolve_tiktok_media(
                    "https://vt.tiktok.com/example", Path(temp_dir) / "images"
                )

        self.assertEqual(result.source_kind, "photo")
        self.assertEqual(result.confidence, "medium")
        self.assertEqual([path.name for path in result.media_paths], ["slide-01.png"])

    def test_extracts_photo_urls_from_embedded_tiktok_json(self) -> None:
        document = {
            "__DEFAULT_SCOPE__": {
                "webapp.video-detail": {
                    "itemInfo": {
                        "itemStruct": {
                            "desc": "Three useful slides",
                            "imagePost": {
                                "images": [
                                    {"imageURL": {"urlList": ["https://cdn.example/1.webp"]}},
                                    {"imageURL": {"urlList": ["https://cdn.example/2.webp"]}},
                                ]
                            },
                        }
                    }
                }
            }
        }
        html = (
            '<html><script id="api-data" type="application/json">'
            + json.dumps(document)
            + "</script></html>"
        )

        extracted = resolver._extract_embedded_post_data(html)

        self.assertEqual(extracted["title"], "Three useful slides")
        self.assertEqual(
            extracted["image_urls"],
            ["https://cdn.example/1.webp", "https://cdn.example/2.webp"],
        )


if __name__ == "__main__":
    unittest.main()
