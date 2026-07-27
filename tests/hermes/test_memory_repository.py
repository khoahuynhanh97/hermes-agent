from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hermes.db import Database


class MemoryRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "hermes.db")
        self.database.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_conversation_context_is_bounded_and_owner_scoped(self) -> None:
        from hermes.memory import MemoryRepository

        memory = MemoryRepository(self.database, max_messages=4, max_chars=500)
        memory.add_message(42, 420, "user", "first")
        memory.add_message(42, 420, "assistant", "second")
        memory.add_message(99, 990, "user", "private-other-owner")
        for index in range(6):
            memory.add_message(42, 420, "user", f"message-{index}")

        context = memory.conversation_context(42, 420)

        self.assertIn("message-5", context)
        self.assertNotIn("first", context)
        self.assertNotIn("private-other-owner", context)
        self.assertLessEqual(len(context), 500)

    def test_pending_memory_is_not_reused_until_approved(self) -> None:
        from hermes.memory import MemoryRepository

        memory = MemoryRepository(self.database)
        proposal = memory.propose(42, "preference", "Prefer concise Vietnamese answers")

        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(memory.approved_context(42, "Vietnamese answers"), "")

        approved = memory.approve(proposal["id"], actor_user_id=42)
        self.assertEqual(approved["status"], "approved")
        self.assertIn("Prefer concise Vietnamese answers", memory.approved_context(42, "Vietnamese"))

        deactivated = memory.deactivate(proposal["id"], actor_user_id=42, reason="changed preference")
        self.assertEqual(deactivated["status"], "deactivated")
        self.assertEqual(memory.approved_context(42, "Vietnamese"), "")
        self.assertEqual(
            [event["action"] for event in memory.list_events(proposal["id"])],
            ["proposed", "approved", "deactivated"],
        )

    def test_owner_cannot_approve_another_users_memory(self) -> None:
        from hermes.memory import MemoryRepository

        memory = MemoryRepository(self.database)
        proposal = memory.propose(42, "fact", "Laptop 1 runs the bot")

        self.assertIsNone(memory.approve(proposal["id"], actor_user_id=99))
        self.assertEqual(memory.get(proposal["id"], owner_user_id=42)["status"], "pending")

    def test_conversation_memory_factory_selects_sqlite_adapter(self) -> None:
        import core.conversation_memory as compatibility

        with patch.dict(
            os.environ,
            {
                "HERMES_STORAGE_BACKEND": "sqlite",
                "HERMES_DB_PATH": str(self.database.path),
            },
        ):
            memory = compatibility.get_memory()
            memory.add(42, "user", "hello from sqlite")
            context = memory.context(42)

        self.assertEqual(type(memory).__name__, "SQLiteConversationMemory")
        self.assertIn("hello from sqlite", context)
        with self.database.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM messages WHERE owner_user_id = '42'"
            ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
