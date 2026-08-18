import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import asyncio

# Import the refactored inbox processing function
from scratch.sync_telegram_jobs import process_inbox

async def main():
    """Entry point for the integrated 10‑minute job.
    It simply invokes the existing ``process_inbox`` logic which:
    1. Connects to Telegram via the userbot.
    2. Retrieves new job messages.
    3. Writes job JSON files to ``.agent_jobs/inbox``.
    4. Disconnects cleanly.
    The surrounding scheduler (cron) will run this script every 10 minutes.
    """
    await process_inbox()

if __name__ == "__main__":
    asyncio.run(main())
