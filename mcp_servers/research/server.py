"""Thin Research MCP facade over Hermes web acquisition services."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from hermes.adapters.sqlite.web_document_repository import SQLiteWebDocumentRepository
from hermes.adapters.web.crawl4ai_fetcher import Crawl4AIWebDocumentFetcher
from hermes.adapters.web.static_fetcher import StaticWebDocumentFetcher
from hermes.application.web_acquisition_service import WebAcquisitionService
from hermes.application.web_document_normalizer import WebDocumentNormalizer
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.db import Database
from hermes.domain.web_document import WebDocument, WebFetchRequest
from hermes.web_research_config import load_web_research_settings_from_env


mcp = FastMCP("hermes-research")


def research_fetch(owner_user_id: str, session_id: str, url: str) -> dict[str, Any]:
    """Acquire one public URL and persist the reference-only source document."""
    owner_user_id, session_id = _required_context(owner_user_id, session_id)
    settings = load_web_research_settings_from_env()
    service = _acquisition_service(settings)
    request = WebFetchRequest(
        owner_user_id=owner_user_id,
        run_id=session_id,
        product_id="research",
        url=url,
        timeout_seconds=settings.timeout_seconds,
        max_html_bytes=settings.max_html_bytes,
        max_markdown_chars=settings.max_markdown_chars,
    )
    document = service.acquire(request)
    stored = _repository().save(document)
    return {"ok": True, **_document_payload(stored)}


def research_extract(html: str, base_url: str = "") -> dict[str, Any]:
    """Normalize supplied HTML deterministically; never summarizes or persists it."""
    if not isinstance(html, str) or not html.strip():
        raise ValueError("html is required")
    settings = load_web_research_settings_from_env()
    result = WebDocumentNormalizer().normalize(
        html,
        base_url=base_url,
        max_markdown_chars=settings.max_markdown_chars,
    )
    return {
        "ok": True,
        "title": result.title,
        "markdown": result.markdown,
        "metadata": result.metadata,
        "content_hash": result.content_hash,
        "warnings": list(result.warnings),
        "dynamic_fallback_recommended": result.dynamic_fallback_recommended,
    }


def research_get_source(owner_user_id: str, source_id: str) -> dict[str, Any]:
    """Read one previously acquired, owner-scoped reference document."""
    owner_user_id = owner_user_id.strip()
    source_id = source_id.strip()
    if not owner_user_id:
        raise ValueError("owner_user_id is required")
    if not source_id:
        raise ValueError("source_id is required")
    document = _repository().get_owned(owner_user_id, source_id)
    if document is None:
        raise ValueError("source_id was not found for owner_user_id")
    return {"ok": True, **_document_payload(document)}


def _acquisition_service(settings: Any) -> WebAcquisitionService:
    policy = PublicWebUrlPolicy()
    static = StaticWebDocumentFetcher(policy=policy)
    crawl4ai = Crawl4AIWebDocumentFetcher(policy=policy) if settings.crawl4ai_enabled else None
    return WebAcquisitionService(static, crawl4ai, settings=settings)


def _repository() -> SQLiteWebDocumentRepository:
    configured = os.environ.get("HERMES_RESEARCH_DB_PATH", "").strip()
    path = Path(configured).expanduser().resolve() if configured else (
        Path(tempfile.gettempdir()) / "hermes-research" / "research.sqlite"
    ).resolve()
    return SQLiteWebDocumentRepository(Database(path))


def _required_context(owner_user_id: str, session_id: str) -> tuple[str, str]:
    owner_user_id = owner_user_id.strip()
    session_id = session_id.strip()
    if not owner_user_id:
        raise ValueError("owner_user_id is required")
    if not session_id:
        raise ValueError("session_id is required")
    return owner_user_id, session_id


def _document_payload(document: WebDocument) -> dict[str, Any]:
    return {
        "source_id": document.id,
        "owner_user_id": document.owner_user_id,
        "session_id": document.run_id,
        "requested_url": document.requested_url,
        "normalized_url": document.final_url,
        "title": document.title,
        "content": document.markdown,
        "metadata": dict(document.metadata),
        "content_hash": document.content_hash,
        "fetch_method": document.acquisition_method,
        "rights_status": document.rights_status,
        "warnings": list(document.warnings),
        "acquired_at": document.acquired_at,
        "provenance": {
            "source_url": document.final_url,
            "acquisition_method": document.acquisition_method,
            "rights_status": document.rights_status,
        },
    }


for _tool in (research_fetch, research_extract, research_get_source):
    mcp.tool()(_tool)


if __name__ == "__main__":
    mcp.run()
