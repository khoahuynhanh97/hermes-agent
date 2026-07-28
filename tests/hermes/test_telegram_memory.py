from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class FakeMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str, **_kwargs):
        self.replies.append(text)

    async def reply_chat_action(self, _action: str):
        return None


class TelegramMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "HERMES_STORAGE_BACKEND": "sqlite",
                "HERMES_DB_PATH": str(Path(self.temp_dir.name) / "hermes.db"),
            },
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def update(text: str = ""):
        message = FakeMessage(text)
        return SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=42),
            effective_chat=SimpleNamespace(id=42),
        )

    def test_remember_command_proposes_then_requires_approval(self) -> None:
        import telegram_bot
        from hermes.memory import MemoryRepository

        update = self.update()
        context = SimpleNamespace(args=["tôi", "thích", "câu", "trả", "lời", "ngắn"])
        asyncio.run(telegram_bot.remember_command(update, context))

        memories = MemoryRepository().list_memories("42")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["status"], "pending")
        self.assertIn("/approve_memory", update.message.replies[0])

        decision_update = self.update()
        decision_context = SimpleNamespace(args=[memories[0]["id"]])
        asyncio.run(telegram_bot.memory_decision_command(decision_update, decision_context, "approve"))
        self.assertEqual(MemoryRepository().get(memories[0]["id"])["status"], "approved")

    def test_natural_memory_request_does_not_call_llm(self) -> None:
        import telegram_bot
        from hermes.memory import MemoryRepository

        update = self.update("Hãy nhớ: tôi ưu tiên câu trả lời bằng tiếng Việt")
        with patch.object(telegram_bot, "ask_gemini", side_effect=AssertionError("LLM must not be called")):
            asyncio.run(telegram_bot.default_chat_handler(update, SimpleNamespace(args=[])))

        memories = MemoryRepository().list_memories("42", status="pending")
        self.assertEqual(len(memories), 1)
        self.assertIn("/approve_memory", update.message.replies[0])

    def test_approve_source_command_approves_all_atomic_lessons(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(default_owner_user_id="42")
        first = store.add_entry(
            title="First",
            source_url="https://example.com/source",
            owner_user_id="42",
            allow_multiple_source_lessons=True,
        )
        store.add_entry(
            title="Second",
            source_url="https://example.com/source",
            owner_user_id="42",
            allow_multiple_source_lessons=True,
        )
        update = self.update()
        asyncio.run(
            telegram_bot.approve_source_command(update, SimpleNamespace(args=[first["id"]]))
        )

        self.assertEqual(len(store.list_entries(status="approved", owner_user_id="42")), 2)
        self.assertIn("2 lesson", update.message.replies[0])

    def test_settings_report_is_redacted(self) -> None:
        import telegram_bot

        update = self.update()
        with patch.object(telegram_bot, "health_check", return_value={"ok": True, "status_code": 200}):
            asyncio.run(telegram_bot.settings_command(update, SimpleNamespace(args=[])))
        rendered = update.message.replies[0]
        self.assertIn("SQLite", rendered)
        self.assertIn("9Router", rendered)
        self.assertNotIn("API_KEY", rendered)

    def test_reanalysis_command_enqueues_pending_lesson_for_its_owner(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(default_owner_user_id="42")
        entry = store.add_entry(
            title="Needs reanalysis",
            source_url="https://example.com/reanalysis",
            owner_user_id="42",
        )
        store.mark_needs_reanalysis(entry["id"], "Source needs review")
        update = self.update()
        job = {
            "job_id": "job-reanalysis",
            "target": {"project_slug": "needs-reanalysis"},
        }
        with patch.object(telegram_bot, "build_video_job", return_value=job) as build:
            asyncio.run(telegram_bot.re_analysis_command(update, SimpleNamespace(args=[entry["id"]])))

        self.assertEqual(build.call_args.kwargs["reanalysis_target_id"], entry["id"])


if __name__ == "__main__":
    unittest.main()
