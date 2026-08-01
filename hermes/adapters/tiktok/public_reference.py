from __future__ import annotations

import hashlib
import json
from http.client import HTTPException
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from hermes.db import utc_now
from hermes.domain.affiliate_research import ReferenceMetadata

_OEMBED_URL = "https://www.tiktok.com/oembed"
_ALLOWED_HOSTS = {"tiktok.com", "www.tiktok.com", "vm.tiktok.com"}
_MAX_RESPONSE_BYTES = 1_048_576
_MAX_TEXT_LENGTHS = {
    "title": 1_000,
    "author_name": 500,
    "author_url": 2_048,
    "thumbnail_url": 2_048,
    "html": 20_000,
}


class InvalidTikTokReferenceError(ValueError):
    """The submitted URL or returned metadata can never succeed unchanged."""


class TikTokReferenceTransportError(RuntimeError):
    """A temporary oEmbed transport failure."""


class _OneRedirectHandler(HTTPRedirectHandler):
    max_redirections = 1


def _stable_reference_id(product_id: str, normalized_url: str) -> str:
    value = f"{product_id}\0{normalized_url}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _normalize_url(url: str) -> str:
    if not isinstance(url, str):
        raise InvalidTikTokReferenceError("TikTok URL must be a string")

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path.rstrip("/")
    if parsed.scheme.lower() != "https" or host not in _ALLOWED_HOSTS:
        raise InvalidTikTokReferenceError(
            "TikTok URL must use an allowed HTTPS TikTok host"
        )
    if not path or path == "/" or ".." in path.split("/"):
        raise InvalidTikTokReferenceError(
            "TikTok URL must identify a public TikTok video"
        )
    if host != "vm.tiktok.com" and not ("/video/" in f"{path}/"):
        raise InvalidTikTokReferenceError(
            "TikTok URL must identify a public TikTok video"
        )
    return urlunsplit(("https", host, path, parsed.query, ""))


def _default_get_json(url: str, **kwargs: Any) -> dict[str, Any]:
    params = kwargs.get("params") or {}
    request_url = f"{url}?{urlencode(params)}" if params else url
    request = Request(request_url, headers={"Accept": "application/json"})
    timeout = min(float(kwargs.get("timeout", 5)), 5.0)
    max_bytes = min(int(kwargs.get("max_bytes", _MAX_RESPONSE_BYTES)), _MAX_RESPONSE_BYTES)
    try:
        with build_opener(_OneRedirectHandler()).open(request, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError("TikTok oEmbed response exceeds maximum length")
            body = response.read(max_bytes + 1)
    except HTTPError as exc:
        if exc.code in {400, 401, 403, 404}:
            raise InvalidTikTokReferenceError(
                "TikTok URL is invalid, unavailable, or unauthorized"
            ) from exc
        raise TikTokReferenceTransportError("TikTok oEmbed request failed") from exc
    except (URLError, HTTPException) as exc:
        raise TikTokReferenceTransportError("TikTok oEmbed request failed") from exc
    if len(body) > max_bytes:
        raise ValueError("TikTok oEmbed response exceeds maximum length")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidTikTokReferenceError(
            "TikTok oEmbed response was not valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise InvalidTikTokReferenceError(
            "TikTok oEmbed response must be an object"
        )
    return payload


class TikTokPublicReferenceAdapter:
    """Retrieve public TikTok oEmbed metadata without downloading media."""

    def __init__(self, get_json: Callable[..., dict[str, Any]] | None = None):
        self._get_json = get_json or _default_get_json

    def fetch(self, url: str, owner_user_id: str, product_id: str) -> ReferenceMetadata:
        normalized_url = _normalize_url(url)
        payload = self._get_json(
            _OEMBED_URL,
            params={"url": normalized_url},
            timeout=5,
            max_bytes=_MAX_RESPONSE_BYTES,
        )
        if not isinstance(payload, dict):
            raise InvalidTikTokReferenceError(
                "TikTok oEmbed response must be an object"
            )
        values = {
            key: self._text(payload, key)
            for key in _MAX_TEXT_LENGTHS
        }
        return ReferenceMetadata(
            id=_stable_reference_id(product_id, normalized_url),
            owner_user_id=owner_user_id,
            product_id=product_id,
            platform="tiktok",
            source_url=normalized_url,
            title=values["title"],
            author_name=values["author_name"],
            author_url=values["author_url"],
            thumbnail_url=values["thumbnail_url"],
            caption=values["title"],
            embed_html=values["html"],
            authorization_scope="public_oembed",
            rights_status="reference_only",
            media_local_path="",
            collected_at=utc_now(),
            source_type="tiktok_oembed",
            content_hash=hashlib.sha256(
                json.dumps(
                    {
                        "source_url": normalized_url,
                        "title": values["title"],
                        "author_name": values["author_name"],
                        "caption": values["title"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )

    @staticmethod
    def _text(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key, "")
        if value is None:
            return ""
        if not isinstance(value, str):
            raise InvalidTikTokReferenceError(
                f"TikTok oEmbed {key} must be text"
            )
        if len(value) > _MAX_TEXT_LENGTHS[key]:
            raise InvalidTikTokReferenceError(
                f"TikTok oEmbed {key} exceeds maximum length"
            )
        return value
