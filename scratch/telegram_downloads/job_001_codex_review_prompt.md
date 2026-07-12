# Codex Review / Prompt for Local Worker

- Job ID: telegram_job_126000 / job_001
- Reviewed at: 2026-07-02 02:07:58
- Source reports:
  - reports/job_001_async_fix.md
  - reports/job_001_already_done_report.md

## Review verdict

Job #001 is complete. Do not rework `telegram_bot.py` for this job.

The worker report states that:
- `ask_gemini()` calls were moved off the asyncio event loop with `run_in_executor`.
- `poll_outbox_loop` now has graceful shutdown via `_stop_event`, `_outbox_task`, and `post_stop`.
- Gemini initialization is performed once at startup.
- `python -m py_compile telegram_bot.py` passed.

The follow-up local report also confirms no further code changes are required for this job.

## Local worker prompt

Proceed to the next improvement task instead of modifying job #001 again.

New task:
Stabilize the Telegram review watcher flow so it reliably performs this loop:

1. Every 3 minutes, read new messages/files from the configured Telegram dialog.
2. Ignore old Telegram history and already-processed message IDs.
3. Download attached `.md`, `.txt`, `.log`, or `.json` worker reports into `reports/telegram_reviews/inbox`.
4. Parse only technical worker reports, not random posts/images.
5. Generate a concise Codex review plus the next actionable local-worker prompt.
6. Send the generated `.md` review/prompt back to Telegram using `TELEGRAM_BOT_TOKEN` and `TELEGRAM_REVIEW_CHAT_ID`.
7. Stop automatically after 5 hours.

Constraints:
- Keep exactly one watcher process running.
- Do not rescan or resend old history unless explicitly requested.
- Do not touch unrelated watchers.
- Keep logs in `reports/telegram_review_watcher.stdout.log` and `reports/telegram_review_watcher.stderr.log`.

Verification:
- Run `python -m py_compile scripts/telegram_review_watcher.py`.
- Start watcher with `scripts/start_telegram_review_watcher.ps1`.
- Confirm exactly one `telegram_review_watcher.py` process is alive.
- Confirm the first scan writes to stdout log and does not send old reviews.
