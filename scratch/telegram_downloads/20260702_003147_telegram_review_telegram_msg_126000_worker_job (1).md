# Telegram Review Proposal

- Created at: 2026-07-02 00:31:47
- Telegram chat: @khoaha_bot
- Message id: 126000
- Message time: 2026-07-01T17:15:55+00:00
- Direction: incoming_bot_message
- Category: worker_job
- Target hint: `telegram_bot.py`

## Tóm tắt nhanh

🔧 CODEX JOB #001 — Fix async + graceful shutdown  File: telegram_bot.py  Task 1 — Fix ask_gemini blocking: Hàm ask_gemini() đang blocking event loop. Wrap tất cả các chỗ gọi ask_gemini() trong story_command, review_command, tech_command, default_chat_handler bằng: result = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, prompt, instruction)   Task 2 — Graceful shutdown poll_outbox_loop: Thêm _stop_event = asyncio.Event() toàn cục. Trong poll_outbox_loop đổi while True thành whil

## Đánh giá reviewer

- Chưa tự động sửa code từ report Telegram.
- Proposal này là checkpoint để reviewer/architect kiểm tra repo, log, artifact, rồi mới quyết định nâng cấp app.
- Nếu report hợp lệ, bước tiếp theo nên là tạo task nhỏ, có scope rõ, rồi verify bằng command phù hợp.

## Rủi ro cần kiểm tra

- Đây có vẻ là yêu cầu handoff cho Codex/Antigravity.
- Cần kiểm tra scope file và output mong muốn trước khi execute.

## Hành động đề xuất

- Mở proposal này trong tab Learning Review của Hermes.
- Nếu là lỗi runtime: trace file/log liên quan trước.
- Nếu là yêu cầu nâng cấp: map vào Manifest -> Task Queue -> Worker -> Artifact flow.
- Nếu là bài học/kinh nghiệm: approve vào knowledge base sau khi đọc kỹ.

## Telegram raw message

```text
🔧 CODEX JOB #001 — Fix async + graceful shutdown

File: telegram_bot.py

Task 1 — Fix ask_gemini blocking:
Hàm ask_gemini() đang blocking event loop. Wrap tất cả các chỗ gọi ask_gemini() trong story_command, review_command, tech_command, default_chat_handler bằng:
result = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, prompt, instruction)


Task 2 — Graceful shutdown poll_outbox_loop:
Thêm _stop_event = asyncio.Event() toàn cục. Trong poll_outbox_loop đổi while True thành while not _stop_event.is_set(). Trong post_init lưu task vào biến để cancel được khi bot dừng.

Task 3 — Init Gemini một lần:
Thêm flag _GEMINI_INITIALIZED = False toàn cục. Gọi init_gemini() một lần trong main() trước khi build app, không gọi lại trong ask_gemini().

Constraints:
- Không đổi public interface của bất kỳ hàm nào
- Không thêm dependency mới
- Giữ nguyên logic business

Expected output: reports/job_001_async_fix.md với diff summary và test notes.

✅ Xong thì upload report lên đây để Claude review tiếp.
```
