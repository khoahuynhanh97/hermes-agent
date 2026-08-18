"""Bounded adapter for a locally hosted TikTok/Douyin crawler.

Hermes owns jobs and artifact storage.  This module only asks the optional
local crawler for public media URLs, then stores a limited photo carousel in
the current job directory.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

import requests
from PIL import Image, UnidentifiedImageError

from hermes.application.core.source_validation import validate_public_url


MAX_CAROUSEL_IMAGES = 20
MAX_CAROUSEL_BYTES = 50 * 1024 * 1024
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
LOCAL_CRAWLER_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass
class TikTokMediaResult:
    source_kind: str
    media_paths: list[Path] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    confidence: str = "needs_source"
    error: str = ""


@dataclass(frozen=True)
class TikTokCrawlerHealth:
    status: str
    compatible: bool
    message: str


def is_tiktok_url(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return host == "tiktok.com" or host.endswith(".tiktok.com")


def is_photo_url(url: str) -> bool:
    return "/photo/" in urlparse(str(url or "")).path.lower()


def resolve_tiktok_media(url: str, output_dir: str | Path) -> TikTokMediaResult:
    """Resolve a TikTok post through the local crawler without leaking data.

    A crawler failure is an expected source-ingestion condition, not a retryable
    worker failure.  Callers can continue with the video path or ask the user
    for the source upload.
    """
    source_kind = "photo" if is_photo_url(url) else "unknown"
    if not is_tiktok_url(url):
        return TikTokMediaResult(source_kind=source_kind, error="Not a TikTok URL.")

    target_dir = Path(output_dir)
    try:
        payload = _call_crawler(url)
    except (OSError, TimeoutError, URLError, ValueError) as exc:
        metadata = _fetch_public_metadata(url)
        resolved_url = str(metadata.get("resolved_url") or "")
        image_urls = metadata.get("image_urls") or []
        if is_photo_url(resolved_url) or image_urls:
            source_kind = "photo"
        if image_urls:
            payload = {
                "type": "image",
                "desc": metadata.get("title", ""),
                "image_data": {"no_watermark_image_list": image_urls},
            }
            fallback_result = _download_photo_carousel(
                payload,
                target_dir,
                confidence="medium",
            )
            fallback_result.metadata = {
                **metadata,
                "acquisition_method": "embedded_page_json",
            }
            if fallback_result.media_paths:
                return fallback_result
        return TikTokMediaResult(
            source_kind=source_kind,
            metadata=metadata,
            error=f"TikTok crawler unavailable: {exc}",
        )

    post_type = str(payload.get("type") or "").lower()
    if post_type in {"image", "photo"}:
        return _download_photo_carousel(payload, target_dir)
    if post_type == "video":
        return TikTokMediaResult(
            source_kind="video",
            metadata=_metadata_from_payload(payload),
            confidence="medium",
        )
    return TikTokMediaResult(
        source_kind=source_kind,
        metadata=_metadata_from_payload(payload),
        error="TikTok crawler did not identify a supported media type.",
    )


def check_crawler_health() -> TikTokCrawlerHealth:
    """Verify that the local process exposes the API contract Hermes uses."""
    try:
        request = Request(
            f"{_crawler_base_url()}/openapi.json",
            headers={"Accept": "application/json", "User-Agent": "HermesLearning/1.0"},
        )
        with urlopen(request, timeout=_timeout_seconds()) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("TikTok crawler OpenAPI response exceeded 2 MB")
        document = json.loads(raw.decode("utf-8"))
        paths = document.get("paths", {}) if isinstance(document, dict) else {}
    except (OSError, TimeoutError, URLError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return TikTokCrawlerHealth("unavailable", False, str(exc))

    endpoint = paths.get("/api/hybrid/video_data") if isinstance(paths, dict) else None
    if not isinstance(endpoint, dict) or "get" not in endpoint:
        return TikTokCrawlerHealth(
            "incompatible",
            False,
            "Crawler is running but /api/hybrid/video_data GET is unavailable.",
        )
    return TikTokCrawlerHealth("ready", True, "Crawler API is ready.")


def _call_crawler(source_url: str) -> dict:
    base_url = _crawler_base_url()

    query = urlencode({"url": source_url, "minimal": "true"})
    request = Request(
        f"{base_url}/api/hybrid/video_data?{query}",
        headers={"Accept": "application/json", "User-Agent": "HermesLearning/1.0"},
    )
    with urlopen(request, timeout=_timeout_seconds()) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("TikTok crawler response exceeded 2 MB")
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("TikTok crawler returned invalid JSON") from exc
    if not isinstance(envelope, dict) or int(envelope.get("code", 200)) != 200:
        raise ValueError("TikTok crawler did not return a successful result")
    payload = envelope.get("data", envelope)
    if not isinstance(payload, dict):
        raise ValueError("TikTok crawler response does not contain post data")
    return payload


def _crawler_base_url() -> str:
    base_url = os.environ.get("TIKTOK_CRAWLER_BASE_URL", "http://127.0.0.1:5556").rstrip("/")
    parsed_base = urlparse(base_url)
    if parsed_base.scheme != "http" or parsed_base.hostname not in LOCAL_CRAWLER_HOSTS:
        raise ValueError("TIKTOK_CRAWLER_BASE_URL must use a localhost HTTP endpoint")
    return base_url


def _download_photo_carousel(
    payload: dict,
    target_dir: Path,
    *,
    confidence: str = "high",
) -> TikTokMediaResult:
    image_data = payload.get("image_data") or {}
    image_urls = image_data.get("no_watermark_image_list") or image_data.get("watermark_image_list") or []
    if not isinstance(image_urls, list) or not image_urls:
        return TikTokMediaResult(
            source_kind="photo",
            metadata=_metadata_from_payload(payload),
            error="TikTok photo post did not include downloadable slides.",
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    total_size = 0
    for index, image_url in enumerate(image_urls[:_max_images()], start=1):
        if not isinstance(image_url, str) or not image_url.startswith(("http://", "https://")):
            continue
        suffix = _image_suffix(image_url)
        destination = target_dir / f"slide-{index:02d}{suffix}"
        try:
            downloaded = _download_image(
                image_url,
                destination,
                max_bytes=max(1, _max_total_bytes() - total_size),
            )
        except (OSError, TimeoutError, URLError, ValueError):
            continue
        try:
            size = downloaded.stat().st_size
        except OSError:
            continue
        if size <= 0 or total_size + size > _max_total_bytes():
            downloaded.unlink(missing_ok=True)
            continue
        paths.append(downloaded)
        total_size += size

    if not paths:
        return TikTokMediaResult(
            source_kind="photo",
            metadata=_metadata_from_payload(payload),
            error="TikTok photo slides could not be downloaded. Upload the images or source video to learn from it.",
        )
    return TikTokMediaResult(
        source_kind="photo",
        media_paths=paths,
        metadata=_metadata_from_payload(payload),
        confidence=confidence,
    )


def _download_image(url: str, destination: Path, *, max_bytes: int) -> Path:
    response = None
    try:
        current_url = url
        for _redirect in range(4):
            validation_error = validate_public_url(current_url)
            if validation_error:
                raise ValueError(validation_error)
            response = requests.get(
                current_url,
                headers={"Accept": "image/*", "User-Agent": "HermesLearning/1.0"},
                timeout=_timeout_seconds(),
                stream=True,
                allow_redirects=False,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location", "")
                response.close()
                response = None
                if not location:
                    raise ValueError("TikTok slide redirect did not contain a destination")
                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            break
        else:
            raise ValueError("TikTok slide exceeded the redirect limit")

        content_type = str(response.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("image/"):
            raise ValueError("TikTok slide response is not an image")
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError("TikTok slide exceeds configured download limit")
        remaining = max_bytes
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=min(64 * 1024, remaining + 1)):
                if not chunk:
                    continue
                if len(chunk) > remaining:
                    raise ValueError("TikTok slide exceeds configured download limit")
                handle.write(chunk)
                remaining -= len(chunk)
        with Image.open(destination) as image:
            image.verify()
    except (OSError, requests.RequestException, UnidentifiedImageError, ValueError):
        destination.unlink(missing_ok=True)
        raise ValueError("TikTok slide did not contain a valid image")
    finally:
        if response is not None:
            response.close()
    return destination


def _fetch_public_metadata(source_url: str) -> dict:
    """Read only bounded public page metadata as a non-evidence fallback."""
    try:
        page = _fetch_impersonated_page(source_url)
        if page is not None:
            raw, resolved_url = page
        else:
            request = Request(source_url, headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=_timeout_seconds()) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                resolved_url = response.geturl()
        if len(raw) > 2 * 1024 * 1024:
            return {"platform": "tiktok", "resolved_url": resolved_url}
        html = raw.decode("utf-8", errors="replace")
        title_match = re.search(r"<title[^>]*>\s*(.*?)\s*</title>", html, re.IGNORECASE | re.DOTALL)
        title = unescape(re.sub(r"\s+", " ", title_match.group(1))).strip() if title_match else ""
        if title.lower() in {"tiktok - make your day", "tiktok"}:
            title = ""
        embedded = _extract_embedded_post_data(html)
        return {
            "platform": "tiktok",
            "resolved_url": resolved_url,
            "title": embedded.get("title") or title,
            "image_urls": embedded.get("image_urls") or [],
        }
    except (OSError, TimeoutError, URLError, ValueError):
        return {}


def _fetch_impersonated_page(source_url: str) -> tuple[bytes, str] | None:
    """Fetch TikTok HTML with curl-cffi when its optional runtime is available."""
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        return None

    response = None
    try:
        current_url = source_url
        for _redirect in range(4):
            validation_error = validate_public_url(current_url)
            if validation_error or not is_tiktok_url(current_url):
                raise ValueError(validation_error or "TikTok page redirected outside TikTok")
            response = curl_requests.get(
                current_url,
                impersonate=os.environ.get("TIKTOK_HTTP_IMPERSONATE", "chrome131_android"),
                allow_redirects=False,
                stream=True,
                timeout=_timeout_seconds(),
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location", "")
                response.close()
                response = None
                if not location:
                    raise ValueError("TikTok page redirect did not contain a destination")
                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            break
        else:
            raise ValueError("TikTok page exceeded the redirect limit")

        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            total += len(chunk)
            if total > 2 * 1024 * 1024:
                raise ValueError("TikTok page exceeded 2 MB")
            chunks.append(chunk)
        return b"".join(chunks), current_url
    except Exception:
        return None
    finally:
        if response is not None:
            response.close()


class _EmbeddedJsonParser(HTMLParser):
    SCRIPT_IDS = {"__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE", "api-data"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.documents: list[str] = []
        self._capturing = False
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "script" and attributes.get("id") in self.SCRIPT_IDS:
            self._capturing = True
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capturing:
            self.documents.append("".join(self._chunks))
            self._capturing = False
            self._chunks = []


def _extract_embedded_post_data(html: str) -> dict:
    """Extract Photo Mode URLs from TikTok's bounded embedded JSON, if present."""
    parser = _EmbeddedJsonParser()
    parser.feed(html)
    for raw_document in parser.documents:
        try:
            document = json.loads(raw_document)
        except (TypeError, json.JSONDecodeError):
            continue
        post = _find_photo_post(document)
        if not post:
            continue
        image_container = post.get("imagePost") or post.get("image_post_info") or {}
        image_urls = []
        for image in image_container.get("images") or []:
            if not isinstance(image, dict):
                continue
            candidates = (
                image.get("imageURL"),
                image.get("displayImage"),
                image.get("display_image"),
            )
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                urls = candidate.get("urlList") or candidate.get("url_list") or []
                if isinstance(urls, list) and urls and isinstance(urls[0], str):
                    image_urls.append(urls[0])
                    break
        if image_urls:
            return {
                "title": str(post.get("desc") or "").strip(),
                "image_urls": image_urls[:_max_images()],
            }
    return {}


def _find_photo_post(value):
    if isinstance(value, dict):
        for key in ("imagePost", "image_post_info"):
            container = value.get(key)
            if isinstance(container, dict) and isinstance(container.get("images"), list):
                return value
        for nested in value.values():
            match = _find_photo_post(nested)
            if match:
                return match
    elif isinstance(value, list):
        for nested in value:
            match = _find_photo_post(nested)
            if match:
                return match
    return None


def _metadata_from_payload(payload: dict) -> dict:
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    return {
        "platform": "tiktok",
        "title": str(payload.get("desc") or "").strip(),
        "description": str(payload.get("desc") or "").strip(),
        "author": str(author.get("nickname") or author.get("unique_id") or "").strip(),
        "music": payload.get("music") or {},
    }


def _image_suffix(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in IMAGE_SUFFIXES else ".jpg"


def _timeout_seconds() -> float:
    try:
        return max(1.0, min(60.0, float(os.environ.get("TIKTOK_CRAWLER_TIMEOUT_SECONDS", "8"))))
    except ValueError:
        return 8.0


def _max_images() -> int:
    try:
        return max(1, min(MAX_CAROUSEL_IMAGES, int(os.environ.get("TIKTOK_MAX_CAROUSEL_IMAGES", "20"))))
    except ValueError:
        return MAX_CAROUSEL_IMAGES


def _max_total_bytes() -> int:
    try:
        value_mb = float(os.environ.get("TIKTOK_MAX_CAROUSEL_MB", "50"))
        return max(1, min(MAX_CAROUSEL_BYTES, int(value_mb * 1024 * 1024)))
    except ValueError:
        return MAX_CAROUSEL_BYTES
