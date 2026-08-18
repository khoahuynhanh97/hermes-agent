from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

from hermes.application.core.source_validation import validate_public_url


class URLInspectionError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    BLOCKED = {"script", "style", "noscript", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self._blocked_depth = 0
        self._in_title = False
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in self.BLOCKED:
            self._blocked_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            values = {str(key).lower(): str(value or "") for key, value in attrs}
            name = values.get("name", "").lower()
            prop = values.get("property", "").lower()
            if name == "description" or prop == "og:description":
                self.description = values.get("content", "").strip()[:1000]

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in self.BLOCKED and self._blocked_depth:
            self._blocked_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str):
        if self._blocked_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._in_title:
            self.title = (self.title + " " + cleaned).strip()[:500]
        else:
            self._text.append(cleaned)

    @property
    def text(self) -> str:
        return "\n".join(self._text)


def inspect_url(
    url: str,
    *,
    timeout_seconds: float = 15,
    max_bytes: int = 2 * 1024 * 1024,
    max_chars: int = 50000,
    max_redirects: int = 3,
) -> dict:
    current = (url or "").strip()
    for _redirect in range(max_redirects + 1):
        validation_error = validate_public_url(current)
        if validation_error:
            raise URLInspectionError(validation_error)
        response = requests.get(
            current,
            headers={"User-Agent": "HermesPersonalAssistant/1.0"},
            timeout=timeout_seconds,
            stream=True,
            allow_redirects=False,
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location", "")
            if not location:
                raise URLInspectionError("Redirect response did not contain a destination")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        break
    else:
        raise URLInspectionError("Too many redirects")

    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"text/html", "text/plain", "application/json"}:
        raise URLInspectionError(f"Unsupported web content type: {content_type or 'unknown'}")
    declared_size = int(response.headers.get("Content-Length") or 0)
    if declared_size > max_bytes:
        raise URLInspectionError("Web source exceeds the configured size limit")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > max_bytes:
            raise URLInspectionError("Web source exceeds the configured size limit")
        chunks.append(chunk)
    encoding = getattr(response, "encoding", None) or "utf-8"
    raw_text = b"".join(chunks).decode(encoding, errors="replace")

    if content_type == "text/html":
        parser = _TextExtractor()
        parser.feed(raw_text)
        title = parser.title
        description = parser.description
        text = parser.text
    else:
        title = ""
        description = ""
        text = raw_text
    text = text.strip()[:max_chars]
    if not text:
        raise URLInspectionError("Web source did not contain readable text")
    return {
        "url": current,
        "title": title,
        "description": description,
        "text": text,
        "content_type": content_type,
        "bytes_read": total,
    }
