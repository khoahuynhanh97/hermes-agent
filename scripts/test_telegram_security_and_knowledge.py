"""Focused regression checks for Telegram auth and pending lesson ownership."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.telegram_auth import is_authorized_user_id, parse_user_ids
import core.knowledge_store as knowledge_store
from core.source_validation import validate_learning_source


def run_tests() -> None:
    assert parse_user_ids("1, 2;3 bad") == {1, 2, 3}
    assert validate_learning_source("https://www.youtube.com/watch?v=test") is None
    assert validate_learning_source("https://www.tiktok.com/@user/video/1") is None
    assert validate_learning_source("https://example.com/video") is not None
    assert validate_learning_source("https://www.instagram.com/reel/example") is not None

    previous = os.environ.get("TELEGRAM_ALLOWED_USER_IDS")
    try:
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "123, 456"
        assert is_authorized_user_id(123)
        assert not is_authorized_user_id(999)
    finally:
        if previous is None:
            os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)
        else:
            os.environ["TELEGRAM_ALLOWED_USER_IDS"] = previous

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old_values = knowledge_store.KB_DIR, knowledge_store.UNIFIED_INDEX_FILE, knowledge_store.ENTRIES_DIR
        knowledge_store.KB_DIR = root
        knowledge_store.UNIFIED_INDEX_FILE = root / "unified_index.json"
        knowledge_store.ENTRIES_DIR = root / "entries"
        try:
            entry = knowledge_store.UnifiedKnowledgeStore().add_entry(
                title="Test lesson",
                source_url="https://example.com/video",
                key_lessons=["Keep the opening concise"],
                owner_user_id=123,
            )
            assert entry["status"] == "pending"
            assert entry["owner_user_id"] == "123"
            assert knowledge_store.UnifiedKnowledgeStore().get_approved_entries() == []
            with patch.object(knowledge_store.UnifiedKnowledgeStore, "_rebuild_style_profile"):
                approved = knowledge_store.UnifiedKnowledgeStore().mark_approved(
                    entry["id"], approved_by="123", approval_mode="test"
                )
                assert approved["approval_history"][-1]["status"] == "approved"
            rejected = knowledge_store.UnifiedKnowledgeStore().mark_rejected(
                entry["id"], rejected_by="123", rejection_reason="test"
            )
            assert rejected["approval_history"][-1]["status"] == "rejected"
        finally:
            knowledge_store.KB_DIR, knowledge_store.UNIFIED_INDEX_FILE, knowledge_store.ENTRIES_DIR = old_values

    print("telegram security and pending knowledge checks: PASS")


if __name__ == "__main__":
    run_tests()
