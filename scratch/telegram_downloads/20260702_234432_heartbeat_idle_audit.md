# Codex Idle Source Audit Prompt

- Reviewed at: 2026-07-02 23:44:32

## Nh?n ??nh
?? qua 3 l?n wakeup li?n ti?p ch?a th?y report h?p l? m?i. Worker n?n ch?y m?t v?ng audit nh? ?? b?o ??m lu?ng Telegram reviewer/worker kh?ng b? l?ch c?u h?nh.

## ?? xu?t fix/upgrade
- Ki?m tra `Reviewer_app/reviewer_app.py`: Bot API, state `last_update_id`, counter `no_report_scan_count`, filter report, log.
- Ki?m tra `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_REVIEW_CHAT_ID`, v? ??ng bot/chat ?ang nh?n report.
- Ki?m tra th? m?c `reports`: state/inbox/reviews c? ghi ???c v? kh?ng spam l?i tin c?.

## Prompt cho worker
Audit nhanh `C:\Work\Code\Upgrade_chat_bot`, t?p trung `Reviewer_app`. Kh?ng refactor l?n. X?c nh?n watcher ??c ??ng Telegram chat b?ng Bot API, kh?ng x? l? l?i message c?, t?o wakeup khi c? report, v? sau 3 l?n kh?ng c? report th? g?i idle audit. Ch?y `python -m py_compile Reviewer_app\reviewer_app.py`, r?i g?i report .md l?n ??ng Telegram bot/chat.
