import sys
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient

# Ensure config/env is loaded
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

API_ID = os.environ.get("TELEGRAM_API_ID")
API_HASH = os.environ.get("TELEGRAM_API_HASH")
PHONE = os.environ.get("TELEGRAM_PHONE")
BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "khoaha_bot")

async def main():
    if not API_ID or not API_HASH:
        print("Error: Missing config in .env")
        return

    session_path = Path("userbot")
    client = TelegramClient(str(session_path), int(API_ID), API_HASH)

    await client.connect()
    if not await client.is_user_authorized():
        print("Error: Userbot is not authorized. Run python scripts/telegram_userbot.py login first.")
        await client.disconnect()
        return

    print(f"📖 Đang đọc lịch sử chat với @{BOT_USERNAME}...")
    
    out_path = Path("scratch/chat_history.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"=== CHAT HISTORY WITH @{BOT_USERNAME} ===\n\n")
        async for message in client.iter_messages(BOT_USERNAME, limit=10):
            sender = "User (Me)" if message.out else f"Bot (@{BOT_USERNAME})"
            f.write(f"[{message.date}] {sender}:\n{message.text}\n")
            f.write("-" * 50 + "\n\n")

    print(f"✅ Đã lưu lịch sử chat vào {out_path}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
