from __future__ import annotations

import re
from dataclasses import dataclass


_EXTERNAL_SEARCH_MARKERS = (
    "tìm thêm",
    "search thêm",
    "mới nhất",
    "github live",
    "search online",
    "trên mạng",
)
_MEMORY_REQUEST = re.compile(
    r"^\s*(?:hãy\s+nhớ|ghi\s+nhớ|nhớ\s+rằng|remember(?:\s+that)?)\s*[:,-]?\s*(.+?)\s*$",
    re.IGNORECASE,
)
_LEARNING_REQUEST = re.compile(
    r"^\s*(?:hãy\s+)?(?:học(?:\s+kiến\s+thức)?|lưu\s+kiến\s+thức|ghi\s+lại\s+kiến\s+thức)"
    r"(?:\s+(?:này|từ\s+nguồn\s+này))?\s*[:,-]?\s*(.+?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AssistantContext:
    prompt: str
    knowledge_context: str = ""
    memory_context: str = ""
    conversation_context: str = ""

    @property
    def has_approved_knowledge(self) -> bool:
        return bool(self.knowledge_context.strip())


def should_search_external(query: str, approved_context: str) -> bool:
    lowered = (query or "").casefold()
    return not approved_context.strip() or any(marker in lowered for marker in _EXTERNAL_SEARCH_MARKERS)


def extract_memory_request(text: str) -> str:
    match = _MEMORY_REQUEST.match(text or "")
    return match.group(1).strip() if match else ""


def extract_learning_request(text: str) -> str:
    match = _LEARNING_REQUEST.match(text or "")
    return match.group(1).strip() if match else ""


class PersonalAssistant:
    """Build the bounded context needed by one personal-assistant response."""

    def __init__(self, knowledge_store, memory_repository):
        self.knowledge_store = knowledge_store
        self.memory_repository = memory_repository

    def build_context(
        self,
        *,
        owner_user_id: str | int,
        chat_id: str | int,
        user_text: str,
    ) -> AssistantContext:
        knowledge = self.knowledge_store.get_approved_context(
            user_text,
            owner_user_id=owner_user_id,
        )
        durable_memory = self.memory_repository.approved_context(owner_user_id, user_text)
        conversation = self.memory_repository.conversation_context(owner_user_id, chat_id)
        blocks = [block for block in (knowledge, durable_memory, conversation) if block]
        blocks.append(f"Current user message:\n{user_text}")
        return AssistantContext(
            prompt="\n\n".join(blocks),
            knowledge_context=knowledge,
            memory_context=durable_memory,
            conversation_context=conversation,
        )
