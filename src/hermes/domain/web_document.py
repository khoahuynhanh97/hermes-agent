from dataclasses import dataclass
from typing import Literal, Mapping, Tuple, Any


class WebFetchFailure(Exception):
    """Base exception for web fetch errors carrying code, detail, and retryable flag."""

    def __init__(self, detail: str, code: str = "transport_error", retryable: bool = False):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.retryable = retryable


class UnsafeWebUrl(WebFetchFailure):
    def __init__(self, detail: str):
        super().__init__(detail=detail, code="unsafe_url", retryable=False)


@dataclass(frozen=True)
class WebFetchRequest:
    owner_user_id: str
    run_id: str
    product_id: str
    url: str
    timeout_seconds: int = 30
    max_html_bytes: int = 2 * 1024 * 1024
    max_markdown_chars: int = 200_000


@dataclass(frozen=True)
class WebDocument:
    id: str
    owner_user_id: str
    run_id: str
    product_id: str
    requested_url: str
    final_url: str
    title: str
    markdown: str
    metadata: Mapping[str, str]
    acquisition_method: Literal["static_http", "crawl4ai"]
    content_hash: str
    rights_status: Literal["reference_only"]
    warnings: Tuple[str, ...]
    acquired_at: str
