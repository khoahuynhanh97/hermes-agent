"""Verify approved technology and repository knowledge is searchable."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from hermes.application.core import knowledge_store


def run_tests():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old_values = knowledge_store.KB_DIR, knowledge_store.UNIFIED_INDEX_FILE, knowledge_store.ENTRIES_DIR
        knowledge_store.KB_DIR = root
        knowledge_store.UNIFIED_INDEX_FILE = root / "unified_index.json"
        knowledge_store.ENTRIES_DIR = root / "entries"
        try:
            store = knowledge_store.UnifiedKnowledgeStore()
            entry = store.add_entry(
                title="Token-saving agent repository",
                source_url="https://www.youtube.com/watch?v=repo-fixture",
                category="technology",
                key_lessons=["Use a context compression workflow before long agent runs."],
                detail_data={
                    "knowledge_type": "github_repo",
                    "search_keywords": ["token saving", "agent context", "repo"],
                    "repositories": [{
                        "name": "context-compressor",
                        "url": "https://github.com/example/context-compressor",
                        "purpose": "Reduce repeated context sent to an AI agent",
                    }],
                    "ai_tools_or_skills": [{
                        "name": "context compression skill",
                        "type": "skill",
                        "purpose": "Keep agent prompts small",
                    }],
                    "how_to_use_in_hermes": "Suggest the repository when the user asks how to reduce agent token usage.",
                },
                owner_user_id=42,
            )
            with patch.object(knowledge_store.UnifiedKnowledgeStore, "_rebuild_style_profile"):
                store.mark_approved(entry["id"], approved_by="42", approval_mode="test")

            context = knowledge_store.UnifiedKnowledgeStore().get_approved_context(
                "tìm repo giúp agent tiết kiệm token", owner_user_id=42
            )
            assert "context-compressor" in context
            assert "https://github.com/example/context-compressor" in context
            assert "Reduce repeated context" in context
            assert "Hermes use:" in context

            other_owner_context = knowledge_store.UnifiedKnowledgeStore().get_approved_context(
                "token saving repo", owner_user_id=99
            )
            assert other_owner_context == ""
        finally:
            knowledge_store.KB_DIR, knowledge_store.UNIFIED_INDEX_FILE, knowledge_store.ENTRIES_DIR = old_values
    print("technology repository knowledge tests: PASS")


if __name__ == "__main__":
    run_tests()
