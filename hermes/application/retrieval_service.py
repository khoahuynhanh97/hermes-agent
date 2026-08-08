"""hermes/application/retrieval_service.py — Knowledge Retrieval & RAG Service.

Encapsulates knowledge retrieval, full-text search, and context injection
for LLM generation pipelines (Hermes Agent Core).
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from hermes.domain.results import Result

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service dedicated to searching, ranking, and preparing knowledge context

    for the Hermes Assistant and LLM Generation pipelines.
    """

    def __init__(self, knowledge_store=None):
        self._store = knowledge_store

    def _get_store(self):
        if self._store is None:
            from core.knowledge_store import get_store
            self._store = get_store()
        return self._store

    def search_knowledge(self, query: str, category: Optional[str] = None, status: str = "approved") -> Result[list[dict[str, Any]]]:
        """Search knowledge entries by query, optionally filtering by category and status."""
        try:
            store = self._get_store()
            entries = store.list_entries(status=status, category=category)
            if not query:
                return Result.success(entries)

            query_tokens = set(query.lower().split())
            results = []
            for entry in entries:
                haystack = f"{entry.get('title', '')} {entry.get('category', '')} {' '.join(entry.get('key_lessons', []))}".lower()
                score = sum(1 for token in query_tokens if token in haystack)
                if score > 0:
                    results.append((score, entry))

            results.sort(key=lambda x: x[0], reverse=True)
            matched_entries = [item[1] for item in results]
            return Result.success(matched_entries)
        except Exception as e:
            logger.error(f"[RetrievalService] Error searching knowledge: {e}")
            return Result.failure("internal_error", str(e))

    def build_rag_context(self, query: str, max_entries: int = 3, owner_user_id: Optional[str] = None) -> str:
        """Build an approved reference block to inject into LLM system prompts."""
        try:
            store = self._get_store()
            if hasattr(store, "get_approved_context"):
                return store.get_approved_context(query=query, max_entries=max_entries, owner_user_id=owner_user_id)
            return ""
        except Exception as e:
            logger.warning(f"[RetrievalService] Error building RAG context: {e}")
            return ""
