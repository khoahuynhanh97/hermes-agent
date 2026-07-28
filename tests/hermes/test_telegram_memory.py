from __future__ import annotations

import asyncio
import json
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

    def test_approve_source_defaults_to_sqlite_when_backend_is_unset(self) -> None:
        import telegram_bot
        from hermes.knowledge import SQLiteKnowledgeStore

        self.env.stop()
        with patch.dict(
            os.environ,
            {"HERMES_DB_PATH": str(Path(self.temp_dir.name) / "default-hermes.db")},
            clear=True,
        ):
            store = SQLiteKnowledgeStore(default_owner_user_id="42")
            entry = store.add_entry(
                title="SQLite default",
                source_url="https://example.com/sqlite-default",
                owner_user_id="42",
            )
            update = self.update()
            approved = asyncio.run(
                telegram_bot.approve_source_command(update, SimpleNamespace(args=[entry["id"]]))
            )

        self.assertEqual(approved, 1)
        self.assertIn("1 lesson", update.message.replies[0])

    def test_approve_source_rejects_non_sqlite_backends(self) -> None:
        import telegram_bot

        self.env.stop()
        with patch.dict(os.environ, {"HERMES_STORAGE_BACKEND": "json"}, clear=True):
            update = self.update()
            approved = asyncio.run(
                telegram_bot.approve_source_command(update, SimpleNamespace(args=["kb-any"]))
            )

        self.assertEqual(approved, 0)
        self.assertIn("SQLite", update.message.replies[0])

    def test_reanalysis_rejects_json_backend_before_creating_a_job(self) -> None:
        import core.knowledge_store as legacy_store
        import telegram_bot

        self.env.stop()
        root = Path(self.temp_dir.name) / "legacy-knowledge"
        with patch.multiple(
            legacy_store,
            KB_DIR=root,
            UNIFIED_INDEX_FILE=root / "unified_index.json",
            ENTRIES_DIR=root / "entries",
        ), patch.dict(
            os.environ, {"HERMES_STORAGE_BACKEND": "json"}, clear=True
        ), patch.object(legacy_store.logger, "info"):
            store = legacy_store.UnifiedKnowledgeStore()
            entry = store.add_entry(
                title="Legacy-only reanalysis",
                source_url="https://example.com/legacy-reanalysis",
                owner_user_id="42",
                detail_data={"legacy": True},
            )
            store.mark_needs_reanalysis(entry["id"], "Legacy source needs review")
            update = self.update()
            with patch.object(
                telegram_bot,
                "enqueue_learning_job",
                side_effect=AssertionError("A JSON-backed reanalysis must not create a job"),
            ):
                result = asyncio.run(
                    telegram_bot.re_analysis_command(update, SimpleNamespace(args=[entry["id"]]))
                )

        self.assertIsNone(result)
        self.assertIn("SQLite", update.message.replies[0])

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

    def test_reanalysis_bypasses_source_dedup_and_records_target_id(self) -> None:
        import telegram_bot
        from core.job_dedup import JobDedup
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(default_owner_user_id="42")
        entry = store.add_entry(
            title="Reanalysis source",
            source_url="https://www.tiktok.com/@owner/video/123",
            owner_user_id="42",
        )
        store.mark_needs_reanalysis(entry["id"], "Source needs review")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            class FakeManager:
                def __init__(self):
                    self.number = 0

                def create_job(self, source_value, source_kind, **_kwargs):
                    self.number += 1
                    output_dir = root / f"output-{self.number}"
                    return {
                        "job_id": f"job-{self.number}",
                        "source": {"value": source_value, "kind": source_kind},
                        "paths": {"job_file": str(root / f"job-{self.number}.json")},
                        "target": {"output_dir": str(output_dir), "project_slug": "reanalysis"},
                    }

                def _write_json(self, path, payload):
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    Path(path).write_text(json.dumps(payload), encoding="utf-8")

            manager = FakeManager()
            dedup = JobDedup(root / "dedup.json")
            with patch.object(telegram_bot, "AgentJobManager", return_value=manager), patch.object(
                telegram_bot, "JOB_DEDUP", dedup
            ), patch.object(telegram_bot.logger, "info"):
                original = telegram_bot.build_video_job(
                    telegram_bot.MODE_LEARN_KNOWLEDGE,
                    entry["source_url"],
                    source_kind="tiktok_url",
                    telegram_info={"chat_id": 42, "user_id": 42},
                )
                reanalysis = asyncio.run(
                    telegram_bot.re_analysis_command(self.update(), SimpleNamespace(args=[entry["id"]]))
                )

        self.assertNotEqual(reanalysis["job_id"], original["job_id"])
        self.assertEqual(reanalysis["reanalysis_target_id"], entry["id"])


if __name__ == "__main__":
    unittest.main()
