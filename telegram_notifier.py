"""
Optional Telegram notifier for affiliate worker.
Reads token + chat_id from .env, gracefully degrades if not configured.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT_IDS = [c.strip() for c in os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if c.strip()]
PRIMARY_CHAT_ID = ALLOWED_CHAT_IDS[0] if ALLOWED_CHAT_IDS else os.environ.get("TELEGRAM_CHAT_ID", "")


class TelegramNotifier:
    def __init__(self):
        self.token = BOT_TOKEN
        self.chat_id = PRIMARY_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)

        if not self.enabled:
            return

        try:
            from telegram import Bot
            self.bot = Bot(token=self.token)
        except Exception:
            self.enabled = False

    def send_batch_summary(self, results):
        if not self.enabled:
            return

        if not results:
            return

        lines = [f"<b>Affiliate Worker -- xu ly {len(results)} san pham</b>\n"]

        for i, r in enumerate(results[:5], 1):
            title = r['title'][:40]
            source = r['source']
            price = r['result']['fetched_metadata'].get('current_price', 0)
            avail = r['result']['fetched_metadata'].get('availability', '?')
            rating = r['result']['fetched_metadata'].get('rating', 0)

            lines.append(f"<b>{i}. [{source}]</b> {title}")
            lines.append(f"   Gia: {price:,.0f} VND | {avail} | Rating: {rating}/5")
            lines.append("")

        if len(results) > 5:
            lines.append(f"... va {len(results) - 5} san pham khac")

        text = "\n".join(lines)

        try:
            import asyncio
            asyncio.run(self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML"))
        except Exception as e:
            print(f"[WARN] Telegram send failed: {e}")
