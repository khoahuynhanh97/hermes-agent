"""Focused checks for the optional local TikTok media resolver."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from hermes.tools import tiktok_media_resolver as resolver


def run_photo_download_check(root: Path) -> None:
    output_dir = root / "job" / "source_images"
    crawler_payload = {
        "type": "image",
        "desc": "A carousel about local AI tools",
        "author": {"nickname": "Author"},
        "image_data": {
            "no_watermark_image_list": [
                "https://cdn.example/slide-01.jpg",
                "https://cdn.example/slide-02.jpg",
            ]
        },
    }

    def fake_download(url: str, destination: Path, **_kwargs) -> Path:
        destination.write_bytes(url.encode("utf-8"))
        return destination

    with patch.object(resolver, "_call_crawler", return_value=crawler_payload), patch.object(
        resolver, "_download_image", side_effect=fake_download
    ):
        result = resolver.resolve_tiktok_media(
            "https://www.tiktok.com/@author/photo/123",
            output_dir,
        )

    assert result.source_kind == "photo"
    assert result.confidence == "high"
    assert [path.name for path in result.media_paths] == ["slide-01.jpg", "slide-02.jpg"]
    assert all(path.parent == output_dir for path in result.media_paths)
    assert result.metadata["title"] == "A carousel about local AI tools"


def run_unavailable_crawler_check(root: Path) -> None:
    with patch.object(resolver, "_call_crawler", side_effect=OSError("connection refused")), patch.object(
        resolver, "_fetch_public_metadata", return_value={"title": "Public TikTok fallback"}
    ):
        result = resolver.resolve_tiktok_media(
            "https://www.tiktok.com/@author/photo/123",
            root / "job" / "source_images",
        )

    assert result.source_kind == "photo"
    assert result.confidence == "needs_source"
    assert not result.media_paths
    assert "unavailable" in result.error.lower()
    assert result.metadata["title"] == "Public TikTok fallback"


def run_tests() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        run_photo_download_check(root)
        run_unavailable_crawler_check(root)
    print("tiktok media resolver checks: PASS")


if __name__ == "__main__":
    run_tests()
