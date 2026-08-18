"""Ensure normal assistant retrieval uses approved lessons only."""

from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from hermes.application.core import knowledge_store


def run_tests():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old_values = knowledge_store.KB_DIR, knowledge_store.UNIFIED_INDEX_FILE, knowledge_store.ENTRIES_DIR
        knowledge_store.KB_DIR = root
        knowledge_store.UNIFIED_INDEX_FILE = root / "unified_index.json"
        knowledge_store.ENTRIES_DIR = root / "entries"
        try:
            store = knowledge_store.UnifiedKnowledgeStore()
            pending = store.add_entry(
                title="Pending Python lesson",
                category="python",
                key_lessons=["pending should not be used"],
                owner_user_id=42,
            )
            approved = store.add_entry(
                title="Approved Python workflow",
                category="python",
                key_lessons=["Use a small virtual environment"],
                owner_user_id=42,
            )
            other_owner = store.add_entry(
                title="Other owner Python lesson",
                category="python",
                key_lessons=["do not expose this"],
                owner_user_id=99,
            )
            rejected = store.add_entry(
                title="Rejected Python lesson",
                category="python",
                key_lessons=["rejected should not be used"],
                owner_user_id=42,
            )
            with patch.object(knowledge_store.UnifiedKnowledgeStore, "_rebuild_style_profile"):
                store.mark_approved(approved["id"], approved_by="42", approval_mode="test")
            store.mark_rejected(rejected["id"], rejected_by="42", rejection_reason="test")

            context = knowledge_store.UnifiedKnowledgeStore().get_approved_context(
                "How do I use a Python workflow?", owner_user_id=42
            )
            assert "Approved Python workflow" in context
            assert "small virtual environment" in context
            assert "Pending Python lesson" not in context
            assert "Rejected Python lesson" not in context
            assert "Other owner Python lesson" not in context
            assert pending["status"] == "pending"
            assert other_owner["status"] == "pending"
        finally:
            knowledge_store.KB_DIR, knowledge_store.UNIFIED_INDEX_FILE, knowledge_store.ENTRIES_DIR = old_values
    print("approved knowledge retrieval tests: PASS")


if __name__ == "__main__":
    run_tests()
