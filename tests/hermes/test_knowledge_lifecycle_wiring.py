from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str, **_kwargs) -> None:
        self.replies.append(text)


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id)
        self.edits: list[str] = []

    async def answer(self, *_args, **_kwargs) -> None:
        return None

    async def edit_message_text(self, text: str, **_kwargs) -> None:
        self.edits.append(text)


class KnowledgeLifecycleWiringTests(unittest.TestCase):
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
    def update(user_id: int = 42) -> SimpleNamespace:
        return SimpleNamespace(
            message=FakeMessage(),
            effective_user=SimpleNamespace(id=user_id),
            effective_chat=SimpleNamespace(id=user_id),
        )

    @staticmethod
    def add_entry(title: str, *, source_url: str = "", owner: str = "42") -> dict:
        from hermes.knowledge import SQLiteKnowledgeStore

        return SQLiteKnowledgeStore(default_owner_user_id=owner).add_entry(
            title=title,
            source_url=source_url or f"https://example.com/{title.lower().replace(' ', '-')}",
            owner_user_id=owner,
            allow_multiple_source_lessons=True,
        )

    def test_telegram_command_constructs_lifecycle_and_approves_lesson(self) -> None:
        import telegram_bot
        from hermes.application.knowledge_lifecycle import KnowledgeLifecycle
        from hermes.knowledge import SQLiteKnowledgeStore

        entry = self.add_entry("Command lifecycle")
        update = self.update()
        with patch.object(
            telegram_bot, "KnowledgeLifecycle", side_effect=KnowledgeLifecycle, create=True
        ) as lifecycle:
            asyncio.run(
                telegram_bot.knowledge_decision_command(
                    update, SimpleNamespace(args=[entry["id"]]), "approve"
                )
            )

        self.assertTrue(lifecycle.called)
        self.assertEqual(SQLiteKnowledgeStore().get_entry(entry["id"])["status"], "approved")
        self.assertIn("approve lesson", update.message.replies[0])

    def test_telegram_callback_constructs_lifecycle_and_rejects_lesson(self) -> None:
        import telegram_bot
        from hermes.application.knowledge_lifecycle import KnowledgeLifecycle
        from hermes.knowledge import SQLiteKnowledgeStore

        entry = self.add_entry("Callback lifecycle")
        query = FakeCallbackQuery(f"knowledge_reject:{entry['id']}")
        update = SimpleNamespace(callback_query=query)
        with patch.object(telegram_bot, "is_authorized_user_id", return_value=True), patch.object(
            telegram_bot, "KnowledgeLifecycle", side_effect=KnowledgeLifecycle, create=True
        ) as lifecycle:
            asyncio.run(telegram_bot.handle_callback(update, SimpleNamespace(bot=None)))

        self.assertTrue(lifecycle.called)
        self.assertEqual(SQLiteKnowledgeStore().get_entry(entry["id"])["status"], "rejected")
        self.assertIn("reject lesson", query.edits[0])

    def test_bulk_approval_constructs_lifecycle_and_approves_visible_lessons(self) -> None:
        import telegram_bot
        from hermes.application.knowledge_lifecycle import KnowledgeLifecycle
        from hermes.knowledge import SQLiteKnowledgeStore

        first = self.add_entry("Cedar lantern")
        second = self.add_entry("Quartz archive")
        update = self.update()
        with patch.object(
            telegram_bot, "KnowledgeLifecycle", side_effect=KnowledgeLifecycle, create=True
        ) as lifecycle:
            asyncio.run(telegram_bot.approve_all_command(update, SimpleNamespace(args=[])))

        store = SQLiteKnowledgeStore()
        self.assertTrue(lifecycle.called)
        self.assertEqual(store.get_entry(first["id"])["status"], "approved")
        self.assertEqual(store.get_entry(second["id"])["status"], "approved")

    def test_source_approval_constructs_lifecycle_and_approves_source_lessons(self) -> None:
        import telegram_bot
        from hermes.application.knowledge_lifecycle import KnowledgeLifecycle
        from hermes.knowledge import SQLiteKnowledgeStore

        first = self.add_entry("Cedar lantern", source_url="https://example.com/source")
        second = self.add_entry("Quartz archive", source_url="https://example.com/source")
        update = self.update()
        with patch.object(
            telegram_bot, "KnowledgeLifecycle", side_effect=KnowledgeLifecycle, create=True
        ) as lifecycle:
            approved = asyncio.run(
                telegram_bot.approve_source_command(update, SimpleNamespace(args=[first["id"]]))
            )

        store = SQLiteKnowledgeStore()
        self.assertTrue(lifecycle.called)
        self.assertEqual(approved, 2)
        self.assertEqual(store.get_entry(first["id"])["status"], "approved")
        self.assertEqual(store.get_entry(second["id"])["status"], "approved")

    def test_force_approval_constructs_lifecycle_and_overrides_duplicate_warning(self) -> None:
        import telegram_bot
        from hermes.application.knowledge_lifecycle import KnowledgeLifecycle
        from hermes.knowledge import SQLiteKnowledgeStore

        approved = self.add_entry("Force lifecycle")
        pending = self.add_entry("Force lifecycle", source_url="https://example.com/force-pending")
        store = SQLiteKnowledgeStore()
        store.mark_approved(approved["id"], approved_by="42", approval_mode="setup")
        update = self.update()
        with patch.object(
            telegram_bot, "KnowledgeLifecycle", side_effect=KnowledgeLifecycle, create=True
        ) as lifecycle:
            asyncio.run(
                telegram_bot.approve_force_command(update, SimpleNamespace(args=[pending["id"]]))
            )

        self.assertTrue(lifecycle.called)
        self.assertEqual(store.get_entry(pending["id"])["status"], "approved")
        self.assertIn("bat chap", update.message.replies[0])

    def test_learning_review_constructs_lifecycle_before_moving_proposal(self) -> None:
        import core.learning_review as learning_review
        from hermes.application.knowledge_lifecycle import KnowledgeLifecycle
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(default_owner_user_id="default")
        source_url = "https://example.com/gui-review"
        entry = store.add_entry(
            title="GUI lifecycle",
            source_url=source_url,
            owner_user_id="default",
        )
        review = learning_review.LearningReviewStore(Path(self.temp_dir.name) / "knowledge")
        proposal = review.create_proposal(
            "GUI lifecycle", f"Source: {source_url}\n# GUI lifecycle\n- Keep this lesson"
        )
        with patch("core.knowledge_store.get_store", return_value=store), patch.object(
            learning_review, "KnowledgeLifecycle", side_effect=KnowledgeLifecycle, create=True
        ) as lifecycle:
            approved_path = review.approve(Path(proposal).name)

        self.assertTrue(lifecycle.called)
        self.assertEqual(store.get_entry(entry["id"])["status"], "approved")
        self.assertTrue(Path(approved_path).is_file())
        self.assertFalse(Path(proposal).exists())

    def test_production_callers_do_not_bypass_lifecycle_transitions(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for path in (root / "telegram_bot.py", root / "core" / "learning_review.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(".mark_approved(", source, path)
            self.assertNotIn(".mark_rejected(", source, path)


if __name__ == "__main__":
    unittest.main()
