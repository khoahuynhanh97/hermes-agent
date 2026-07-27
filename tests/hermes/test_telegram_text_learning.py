from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class TelegramTextLearningTests(unittest.TestCase):
    def test_learn_alias_always_selects_knowledge_mode(self) -> None:
        import telegram_bot

        update = SimpleNamespace(message=SimpleNamespace(text="/learn repository maps"))
        context = SimpleNamespace(args=["repository", "maps"])
        with patch.object(telegram_bot, "create_video_job_command", new=AsyncMock()) as create:
            asyncio.run(telegram_bot.hoc_kien_thuc_command(update, context))
        self.assertEqual(create.await_args.kwargs["mode"], telegram_bot.MODE_LEARN_KNOWLEDGE)

    def test_plain_text_source_is_written_to_local_data_directory(self) -> None:
        import telegram_bot

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"HERMES_DATA_DIR": temp_dir}
        ):
            path, metadata = telegram_bot.save_text_learning_source(
                "Repository maps reduce repeated context.", owner_user_id=42
            )

            self.assertTrue(path.is_file())
            self.assertTrue(str(path).startswith(str(Path(temp_dir).resolve())))
            self.assertEqual(path.read_text(encoding="utf-8"), "Repository maps reduce repeated context.")
            self.assertTrue(metadata["sha256"])

    def test_natural_learning_request_routes_to_learning_job(self) -> None:
        import telegram_bot

        message = SimpleNamespace(
            text="Hãy học kiến thức này: Repository maps reduce token use",
            reply_chat_action=AsyncMock(),
        )
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=42),
            effective_chat=SimpleNamespace(id=42),
        )
        with patch.object(telegram_bot, "create_video_job_command", new=AsyncMock()) as create:
            asyncio.run(telegram_bot.default_chat_handler(update, SimpleNamespace(args=[])))
        self.assertEqual(create.await_args.kwargs["mode"], telegram_bot.MODE_LEARN_KNOWLEDGE)


if __name__ == "__main__":
    unittest.main()
