# Codex Idle Source Audit Prompt

- Reviewed at: 2026-07-03 00:19:46

## Assessment
There have been 3 consecutive wakeups without a valid worker report. Run a light audit to make sure the Telegram reviewer/worker loop is still healthy.

## Fix / Upgrade Proposal
- Check `Reviewer_app/reviewer_app.py`: Bot API polling, `last_update_id`, `no_report_scan_count`, report filtering, and logs.
- Check `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_REVIEW_CHAT_ID`, and whether the worker is sending reports to the correct bot/chat.
- Check `reports`: state, inbox, and reviews should be writable and should not reprocess old messages.

## Worker Prompt
Audit `C:\Work\Code\Upgrade_chat_bot`, focusing on `Reviewer_app`. Do not do a large refactor. Confirm the watcher reads the correct Telegram chat via Bot API, avoids old messages, creates wakeups for valid reports, and sends idle audit after 3 scans without a valid report. Run `python -m py_compile Reviewer_app\reviewer_app.py`, then send a markdown report to the correct Telegram bot/chat.
