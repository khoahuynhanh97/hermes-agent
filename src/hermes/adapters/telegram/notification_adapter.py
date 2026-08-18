from __future__ import annotations

from typing import Any

from hermes.domain.results import Result


class TelegramNotificationAdapter:
    def __init__(self, bot):
        self.bot = bot

    def publish(self, event: dict[str, Any]) -> Result[None]:
        if self.bot is None:
            return Result.failure("unavailable", "Telegram bot is not initialized.")
        try:
            chat_id = event.get("chat_id")
            text = event.get("message", "")
            if chat_id and text:
                self.bot.send_message(chat_id=chat_id, text=text)
            return Result.success(None)
        except Exception as e:
            return Result.failure("unavailable", str(e))