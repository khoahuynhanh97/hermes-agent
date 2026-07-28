from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hermes.application.knowledge_lifecycle import KnowledgeLifecycle, LifecycleActor


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


class RecordingKnowledgeLifecycle(KnowledgeLifecycle):
    calls: list[tuple] = []

    @classmethod
    def reset(cls) -> None:
        cls.calls = []

    def approve(self, lesson_id, actor, mode="", *, force=False):
        self.calls.append(("approve", lesson_id, actor, mode, force))
        return super().approve(lesson_id, actor, mode, force=force)

    def reject(self, lesson_id, actor, reason=""):
        self.calls.append(("reject", lesson_id, actor, reason))
        return super().reject(lesson_id, actor, reason)

    def request_reanalysis(self, lesson_id, actor, *, reason="", metadata=None):
        self.calls.append(("request_reanalysis", lesson_id, actor, reason, metadata or {}))
        return super().request_reanalysis(
            lesson_id, actor, reason=reason, metadata=metadata
        )

    def apply(self, commands):
        command_list = tuple(commands)
        self.calls.append(("apply", command_list))
        return super().apply(command_list)


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
        RecordingKnowledgeLifecycle.reset()

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

    @staticmethod
    def event_actions(store, entry_id: str) -> list[str]:
        return [event["action"] for event in store.list_events(entry_id)]

    def test_telegram_command_approves_with_owner_lifecycle_actor(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        entry = self.add_entry("Command lifecycle")
        update = self.update()
        with patch.object(telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle):
            asyncio.run(
                telegram_bot.knowledge_decision_command(
                    update, SimpleNamespace(args=[entry["id"]]), "approve"
                )
            )

        self.assertEqual(
            RecordingKnowledgeLifecycle.calls[:1],
            [("approve", entry["id"], LifecycleActor.owner("42"), "telegram_command", False)],
        )
        self.assertEqual(SQLiteKnowledgeStore().get_entry(entry["id"])["status"], "approved")

    def test_telegram_callback_rejects_with_owner_lifecycle_actor(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        entry = self.add_entry("Callback lifecycle")
        query = FakeCallbackQuery(f"knowledge_reject:{entry['id']}")
        with patch.object(telegram_bot, "is_authorized_user_id", return_value=True), patch.object(
            telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle
        ):
            asyncio.run(
                telegram_bot.handle_callback(
                    SimpleNamespace(callback_query=query), SimpleNamespace(bot=None)
                )
            )

        self.assertEqual(
            RecordingKnowledgeLifecycle.calls[:1],
            [("reject", entry["id"], LifecycleActor.owner("42"), "Rejected via Telegram")],
        )
        self.assertEqual(SQLiteKnowledgeStore().get_entry(entry["id"])["status"], "rejected")

    def test_bulk_approval_skips_reanalysis_and_approves_eligible_lessons(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        eligible = self.add_entry("Cedar lantern")
        flagged = self.add_entry("Quartz archive")
        store = SQLiteKnowledgeStore()
        store.mark_needs_reanalysis(flagged["id"], "Source needs repair")
        update = self.update()
        with patch.object(telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle):
            asyncio.run(telegram_bot.approve_all_command(update, SimpleNamespace(args=[])))

        self.assertEqual(len(RecordingKnowledgeLifecycle.calls), 1)
        method, commands = RecordingKnowledgeLifecycle.calls[0]
        self.assertEqual(method, "apply")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].lesson_id, eligible["id"])
        self.assertEqual(commands[0].actor, LifecycleActor.owner("42"))
        self.assertEqual(store.get_entry(eligible["id"])["status"], "approved")
        self.assertEqual(store.get_entry(flagged["id"])["status"], "pending")
        self.assertIn("Da approve 1 lesson", update.message.replies[0])
        self.assertIn("Bo qua 1 lesson can reanalysis", update.message.replies[0])

    def test_source_approval_applies_owner_lifecycle_batch(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        first = self.add_entry("Cedar lantern", source_url="https://example.com/source")
        second = self.add_entry("Quartz archive", source_url="https://example.com/source")
        update = self.update()
        with patch.object(telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle):
            approved = asyncio.run(
                telegram_bot.approve_source_command(update, SimpleNamespace(args=[first["id"]]))
            )

        method, commands = RecordingKnowledgeLifecycle.calls[0]
        self.assertEqual(method, "apply")
        self.assertEqual([command.actor for command in commands], [LifecycleActor.owner("42")] * 2)
        store = SQLiteKnowledgeStore()
        self.assertEqual(approved, 2)
        self.assertEqual(store.get_entry(first["id"])["status"], "approved")
        self.assertEqual(store.get_entry(second["id"])["status"], "approved")

    def test_force_approval_uses_force_lifecycle_command(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        approved = self.add_entry("Force lifecycle")
        pending = self.add_entry("Force lifecycle", source_url="https://example.com/force-pending")
        store = SQLiteKnowledgeStore()
        store.mark_approved(approved["id"], approved_by="42", approval_mode="setup")
        with patch.object(telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle):
            asyncio.run(
                telegram_bot.approve_force_command(
                    self.update(), SimpleNamespace(args=[pending["id"]])
                )
            )

        self.assertEqual(
            RecordingKnowledgeLifecycle.calls[:1],
            [("approve", pending["id"], LifecycleActor.owner("42"), "force_approve", True)],
        )
        self.assertEqual(store.get_entry(pending["id"])["status"], "approved")

    def test_reanalysis_uses_idempotent_owner_lifecycle_request_before_enqueue(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        entry = self.add_entry("Reanalysis lifecycle")
        store = SQLiteKnowledgeStore()
        store.mark_needs_reanalysis(entry["id"], "Source needs repair")
        job = {"job_id": "reanalysis", "target": {"project_slug": "test"}}
        with patch.object(telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle), patch.object(
            telegram_bot, "enqueue_learning_job", return_value=job
        ) as enqueue:
            result = asyncio.run(
                telegram_bot.re_analysis_command(
                    self.update(), SimpleNamespace(args=[entry["id"]])
                )
            )

        self.assertEqual(result, job)
        self.assertEqual(
            RecordingKnowledgeLifecycle.calls[:1],
            [
                (
                    "request_reanalysis",
                    entry["id"],
                    LifecycleActor.owner("42"),
                    "Reanalysis requested via Telegram",
                    {},
                )
            ],
        )
        self.assertEqual(enqueue.call_args.kwargs["reanalysis_target_id"], entry["id"])
        self.assertEqual(self.event_actions(store, entry["id"]), ["created", "reanalysis_requested"])

    def test_reanalysis_refuses_wrong_owner_before_enqueue(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        entry = self.add_entry("Private reanalysis", owner="99")
        store = SQLiteKnowledgeStore(default_owner_user_id="99")
        store.mark_needs_reanalysis(entry["id"], "Source needs repair")
        with patch.object(telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle), patch.object(
            telegram_bot,
            "enqueue_learning_job",
            side_effect=AssertionError("must not enqueue foreign lessons"),
        ):
            result = asyncio.run(
                telegram_bot.re_analysis_command(
                    self.update(), SimpleNamespace(args=[entry["id"]])
                )
            )

        self.assertIsNone(result)
        self.assertEqual(RecordingKnowledgeLifecycle.calls[0][0], "request_reanalysis")
        self.assertEqual(RecordingKnowledgeLifecycle.calls[0][2], LifecycleActor.owner("42"))
        self.assertEqual(self.event_actions(store, entry["id"]), ["created", "reanalysis_requested"])

    def test_reanalysis_rejects_invalid_state_without_lifecycle_mutation(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        entry = self.add_entry("Approved reanalysis")
        store = SQLiteKnowledgeStore()
        store.mark_approved(entry["id"], approved_by="42", approval_mode="setup")
        with patch.object(telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle), patch.object(
            telegram_bot,
            "enqueue_learning_job",
            side_effect=AssertionError("must not enqueue approved lessons"),
        ):
            result = asyncio.run(
                telegram_bot.re_analysis_command(
                    self.update(), SimpleNamespace(args=[entry["id"]])
                )
            )

        self.assertIsNone(result)
        self.assertEqual(RecordingKnowledgeLifecycle.calls, [])
        self.assertEqual(store.get_entry(entry["id"])["status"], "approved")
        self.assertEqual(self.event_actions(store, entry["id"]), ["created", "approved"])

    def test_reanalysis_rejects_pending_lesson_without_reanalysis_flag_before_mutation(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        entry = self.add_entry("Pending without reanalysis")
        store = SQLiteKnowledgeStore()
        with patch.object(telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle), patch.object(
            telegram_bot,
            "enqueue_learning_job",
            return_value={"job_id": "unexpected"},
        ) as enqueue:
            result = asyncio.run(
                telegram_bot.re_analysis_command(
                    self.update(), SimpleNamespace(args=[entry["id"]])
                )
            )

        self.assertIsNone(result)
        enqueue.assert_not_called()
        self.assertEqual(RecordingKnowledgeLifecycle.calls, [])
        self.assertFalse(store.get_entry(entry["id"])["needs_reanalysis"])
        self.assertEqual(self.event_actions(store, entry["id"]), ["created"])

    def test_reanalysis_rejects_flagged_lesson_without_source_before_mutation(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore()
        entry = store.add_entry(title="Source-less reanalysis", owner_user_id="42")
        store.mark_needs_reanalysis(entry["id"], "Source needs repair")
        with patch.object(telegram_bot, "KnowledgeLifecycle", RecordingKnowledgeLifecycle), patch.object(
            telegram_bot,
            "enqueue_learning_job",
            side_effect=AssertionError("must not enqueue lessons without a source"),
        ):
            result = asyncio.run(
                telegram_bot.re_analysis_command(
                    self.update(), SimpleNamespace(args=[entry["id"]])
                )
            )

        self.assertIsNone(result)
        self.assertEqual(RecordingKnowledgeLifecycle.calls, [])
        self.assertTrue(store.get_entry(entry["id"])["needs_reanalysis"])
        self.assertEqual(self.event_actions(store, entry["id"]), ["created", "reanalysis_requested"])

    def test_learning_review_approval_uses_system_lifecycle_actor_before_move(self) -> None:
        import core.learning_review as learning_review
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(default_owner_user_id="default")
        source_url = "https://example.com/gui-review"
        entry = store.add_entry(title="GUI lifecycle", source_url=source_url, owner_user_id="default")
        review = learning_review.LearningReviewStore(Path(self.temp_dir.name) / "knowledge")
        proposal = review.create_proposal(
            "GUI lifecycle", f"Source: {source_url}\n# GUI lifecycle\n- Keep this lesson"
        )
        with patch("core.knowledge_store.get_store", return_value=store), patch.object(
            learning_review, "KnowledgeLifecycle", RecordingKnowledgeLifecycle
        ):
            approved_path = review.approve(Path(proposal).name)

        self.assertEqual(
            RecordingKnowledgeLifecycle.calls[:1],
            [("approve", entry["id"], LifecycleActor.system("gui-review"), "manual", False)],
        )
        self.assertEqual(store.get_entry(entry["id"])["status"], "approved")
        self.assertEqual(store.list_events(entry["id"])[-1]["actor_user_id"], "gui-review")
        self.assertTrue(Path(approved_path).is_file())
        self.assertFalse(Path(proposal).exists())

    def test_learning_review_rejection_uses_system_lifecycle_actor_before_move(self) -> None:
        import core.learning_review as learning_review
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(default_owner_user_id="default")
        source_url = "https://example.com/gui-reject"
        entry = store.add_entry(title="GUI rejection", source_url=source_url, owner_user_id="default")
        review = learning_review.LearningReviewStore(Path(self.temp_dir.name) / "knowledge")
        proposal = review.create_proposal("GUI rejection", f"Source: {source_url}\n# Reject")
        with patch("core.knowledge_store.get_store", return_value=store), patch.object(
            learning_review, "KnowledgeLifecycle", RecordingKnowledgeLifecycle
        ):
            rejected_path = review.reject(Path(proposal).name)

        self.assertEqual(
            RecordingKnowledgeLifecycle.calls[:1],
            [
                (
                    "reject",
                    entry["id"],
                    LifecycleActor.system("gui-review"),
                    "Rejected via review queue UI",
                )
            ],
        )
        self.assertEqual(store.get_entry(entry["id"])["status"], "rejected")
        self.assertEqual(store.list_events(entry["id"])[-1]["actor_user_id"], "gui-review")
        self.assertTrue(Path(rejected_path).is_file())
        self.assertFalse(Path(proposal).exists())

    def test_learning_review_rejection_without_matching_lesson_does_not_move_proposal(self) -> None:
        import core.learning_review as learning_review
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(default_owner_user_id="default")
        review = learning_review.LearningReviewStore(Path(self.temp_dir.name) / "knowledge")
        proposal = review.create_proposal(
            "No matching lesson", "Source: https://example.com/missing\n# Reject"
        )
        with patch("core.knowledge_store.get_store", return_value=store):
            with self.assertRaisesRegex(ValueError, "Knowledge lesson not found"):
                review.reject(Path(proposal).name)

        self.assertTrue(Path(proposal).is_file())
        self.assertFalse((review.rejected_dir / Path(proposal).name).exists())

    def test_gui_auto_approval_uses_system_lifecycle_actor(self) -> None:
        import core.knowledge_base as knowledge_base
        from hermes.knowledge import SQLiteKnowledgeStore

        root = Path(self.temp_dir.name) / "knowledge-base"
        downloaded = Path(self.temp_dir.name) / "source.mp3"
        downloaded.write_bytes(b"audio")
        analysis = json.dumps(
            {
                "title": "GUI auto approval",
                "platform": "youtube",
                "key_lessons": ["Use the lifecycle seam."],
            }
        )
        with patch.object(knowledge_base, "KB_DIR", str(root)), patch.object(
            knowledge_base, "INDEX_FILE", str(root / "index.json")
        ), patch.object(knowledge_base, "TEMP_DL_DIR", str(root / "temp")), patch.object(
            knowledge_base, "download_video", return_value=str(downloaded)
        ), patch.object(knowledge_base, "analyze_video", return_value=analysis), patch.object(
            knowledge_base, "KnowledgeLifecycle", RecordingKnowledgeLifecycle, create=True
        ):
            result = knowledge_base.learn_from_url(
                "https://example.com/gui-auto", auto_approve=True, approved_by="gui_user", approval_mode="auto"
            )

        self.assertTrue(result["success"])
        store = SQLiteKnowledgeStore()
        entry = store.list_entries(status="approved")[0]
        self.assertEqual(
            RecordingKnowledgeLifecycle.calls[:1],
            [("approve", entry["id"], LifecycleActor.system("gui-review"), "auto", False)],
        )
        self.assertEqual(store.list_events(entry["id"])[-1]["actor_user_id"], "gui-review")

    def test_production_callers_do_not_bypass_lifecycle_transitions(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for path in (
            root / "telegram_bot.py",
            root / "core" / "learning_review.py",
            root / "core" / "knowledge_base.py",
        ):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(".mark_approved(", source, path)
            self.assertNotIn(".mark_rejected(", source, path)


if __name__ == "__main__":
    unittest.main()
