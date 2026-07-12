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
BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "khoaha_bot")

async def main():
    if not API_ID or not API_HASH:
        print("Error: Missing config in .env")
        return

    session_path = Path("userbot")
    client = TelegramClient(str(session_path), int(API_ID), API_HASH)

    await client.connect()
    if not await client.is_user_authorized():
        print("Error: Userbot is not authorized.")
        await client.disconnect()
        return

    print("Checking latest message for attachments...")
    async for message in client.iter_messages(BOT_USERNAME, limit=1):
        print(f"Message ID: {message.id}")
        print(f"Date: {message.date}")
        print(f"Text/Caption: {message.text}")
        print(f"Has media: {message.media is not None}")
        
        if message.media:
            print(f"Media type: {type(message.media)}")
            # Download media
            download_dir = Path("scratch/telegram_downloads")
            download_dir.mkdir(parents=True, exist_ok=True)
            path = await message.download_media(str(download_dir))
            print(f"✅ Downloaded attachment to: {path}")
            
            # If it's a text/markdown file, let's print its contents
            if path and path.endswith(('.txt', '.md', '.json')):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    print("\n=== ATTACHMENT CONTENTS ===")
                    print(f.read())
                    print("===========================")
        else:
            print("No media attached to this message.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
