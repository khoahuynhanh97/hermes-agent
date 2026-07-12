import sys
import os
import re
import json
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

PROCESSED_FILE = Path("scratch/processed_messages.json")
SETTINGS_FILE = Path("scratch/agent_settings.json")

def load_processed_ids():
    if PROCESSED_FILE.exists():
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_processed_id(msg_id):
    processed = load_processed_ids()
    processed.add(msg_id)
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(processed), f, indent=2)

def is_agent_enabled():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
                return settings.get("enabled", True)
        except Exception:
            pass
    return True

async def process_inbox():
    if not is_agent_enabled():
        print("Agent settings: disabled.")
        return

    if not API_ID or not API_HASH:
        print("Error: Missing API_ID or API_HASH in .env")
        return

    session_path = Path("userbot")
    client = TelegramClient(str(session_path), int(API_ID), API_HASH)

    await client.connect()
    if not await client.is_user_authorized():
        print("Error: Userbot not authorized.")
        await client.disconnect()
        return

    processed_ids = load_processed_ids()
    
    new_jobs_count = 0
    async for message in client.iter_messages(BOT_USERNAME, limit=50):
        # Check if the message contains a markdown file attachment (.md)
        is_md_attachment = False
        if message.media:
            # Telethon document check
            document = getattr(message.media, 'document', None)
            if document:
                for attr in getattr(document, 'attributes', []):
                    file_name = getattr(attr, 'file_name', '')
                    if file_name and file_name.lower().endswith('.md'):
                        is_md_attachment = True
                        break

        # Look for CODEX JOB or review proposal keywords or md attachment
        is_job_message = False
        if not message.out:
            text_lower = (message.text or "").lower()
            if ("codex job" in text_lower or
                "review proposal" in text_lower or
                "review" in text_lower or
                "proposal" in text_lower or
                is_md_attachment):
                is_job_message = True
                
        if is_job_message and message.id not in processed_ids:
            msg_id = message.id
            msg_text = message.text or ""
            
            prompt_content = msg_text
            # If there's an attachment, download and parse it
            if message.media:
                download_dir = Path("scratch/telegram_downloads")
                download_dir.mkdir(parents=True, exist_ok=True)
                path = await message.download_media(str(download_dir))
                if path and os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            attachment_content = f.read()
                        prompt_content = f"--- Telegram Caption ---\n{msg_text}\n\n--- Attachment Content ---\n{attachment_content}"
                    except Exception as e:
                        print(f"Error reading attachment: {e}")
            
            # Extract Job ID or Number (search in both caption and attachment)
            job_num_match = re.search(r"CODEX JOB #?(\d+)", prompt_content)
            if not job_num_match:
                job_num_match = re.search(r"job_?(\d+)", prompt_content, re.IGNORECASE)
            job_num = job_num_match.group(1) if job_num_match else str(msg_id)
            job_id = f"job_telegram_{job_num}"
            
            # Extract Target File Name
            file_match = re.search(r"\*\*File:\*\*\s*`?(.*?)`?\n", prompt_content, re.IGNORECASE)
            if not file_match:
                file_match = re.search(r"Target hint:\s*`?(.*?)`?\n", prompt_content, re.IGNORECASE)
            target_file_name = "telegram_bot.py"
            if file_match:
                target_file_name = file_match.group(1).strip()

            print(f"📥 Đồng bộ Job mới từ Telegram: {job_id} (Msg ID: {msg_id})")
            
            # Define directories
            project_slug = "vt-tiktok-com-zscmpyqun" # default active project
            output_dir = Path("projects") / project_slug / "agent_outputs" / job_id
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Write the worker prompt file
            prompt_path = output_dir / "antigravity_codex_prompt.md"
            prompt_path.write_text(prompt_content, encoding="utf-8")
            # Write standard Inbox Job JSON
            inbox_dir = Path(".agent_jobs/inbox")
            inbox_dir.mkdir(parents=True, exist_ok=True)
            job_data = {
                "job_id": job_id,
                "status": "pending",
                "telegram_message_id": msg_id,
                "target": {
                    "project_slug": project_slug,
                    "output_dir": str(output_dir.resolve()),
                    "file_to_modify": target_file_name
                },
                "paths": {
                    "worker_prompt": str(prompt_path.resolve())
                }
            }
            
            job_file = inbox_dir / f"{job_id}.json"
            with open(job_file, "w", encoding="utf-8") as f:
                json.dump(job_data, f, ensure_ascii=False, indent=2)
            
            # Save processed ID so we don't sync again
            save_processed_id(msg_id)
            new_jobs_count += 1

    if new_jobs_count == 0:
        print("No new jobs found on Telegram.")
    else:
        print(f"Successfully synchronized {new_jobs_count} new job(s) from Telegram.")

    await client.disconnect()

async def main():
    await process_inbox()

if __name__ == "__main__":
    asyncio.run(main())
