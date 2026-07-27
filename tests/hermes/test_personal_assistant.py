from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes.db import Database
from hermes.knowledge import SQLiteKnowledgeStore
from hermes.memory import MemoryRepository


class PersonalAssistantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "hermes.db")
        self.database.initialize()
        self.knowledge = SQLiteKnowledgeStore(self.database)
        self.memory = MemoryRepository(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_context_uses_only_approved_knowledge_and_memory(self) -> None:
        from hermes.assistant import PersonalAssistant

        approved = self.knowledge.add_entry(
            title="Repository maps",
            source_url="https://example.com/approved",
            key_lessons=["Repository maps reduce repeated context loading."],
            detail_data={"summary": "Repository maps reduce token use."},
            owner_user_id="42",
        )
        self.knowledge.mark_approved(approved["id"], approved_by="42")
        self.knowledge.add_entry(
            title="Pending secret",
            source_url="https://example.com/pending",
            key_lessons=["This must not be used."],
            owner_user_id="42",
        )
        approved_memory = self.memory.propose("42", "preference", "Prefer concise Vietnamese answers")
        self.memory.approve(approved_memory["id"], "42")
        self.memory.propose("42", "fact", "Pending memory must not be used")
        self.memory.add_message("42", "chat-1", "user", "Earlier question")

        context = PersonalAssistant(self.knowledge, self.memory).build_context(
            owner_user_id="42",
            chat_id="chat-1",
            user_text="How can repository maps save tokens?",
        )

        self.assertIn("Repository maps", context.prompt)
        self.assertIn("Prefer concise Vietnamese answers", context.prompt)
        self.assertIn("Earlier question", context.prompt)
        self.assertNotIn("Pending secret", context.prompt)
        self.assertNotIn("Pending memory must not be used", context.prompt)

    def test_external_search_is_used_only_when_needed_or_requested(self) -> None:
        from hermes.assistant import should_search_external

        self.assertFalse(should_search_external("find a token saving repo", "approved knowledge"))
        self.assertTrue(should_search_external("find a token saving repo", ""))
        self.assertTrue(should_search_external("tìm thêm repo mới nhất", "approved knowledge"))

    def test_explicit_natural_memory_request_is_extracted(self) -> None:
        from hermes.assistant import extract_learning_request, extract_memory_request

        self.assertEqual(
            extract_memory_request("Hãy nhớ: tôi thích câu trả lời ngắn gọn"),
            "tôi thích câu trả lời ngắn gọn",
        )
        self.assertEqual(extract_memory_request("Tôi thích câu trả lời ngắn gọn"), "")
        self.assertEqual(
            extract_learning_request("Hãy học kiến thức này: Repository maps reduce token use"),
            "Repository maps reduce token use",
        )
        self.assertEqual(extract_learning_request("Repository maps reduce token use"), "")


if __name__ == "__main__":
    unittest.main()
