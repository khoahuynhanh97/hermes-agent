# Reviewer App Wakeup Result

- Source chat id: 5069349064
- Message id: 9694
- Category: worker_job
- Source kind: document
- Source file: job_001_async_fix.md
- Downloaded path: C:\Work\Code\Upgrade_chat_bot\Reviewer_app\reports\telegram_inbox\20260702_133636_msg_9694_job_001_async_fix.md
- Wakeup prompt created at: 2026-07-02 13:36:39

# Codex Review Wakeup

Day la prompt danh thuc Codex reviewer. Reviewer_app chi chuyen report va yeu cau, khong tu review va khong tu sua code.

## Context

- Source chat id: 5069349064
- Message id: 9694
- Category: worker_job
- Source kind: document
- Source file: job_001_async_fix.md
- Downloaded path: C:\Work\Code\Upgrade_chat_bot\Reviewer_app\reports\telegram_inbox\20260702_133636_msg_9694_job_001_async_fix.md
- Created at: 2026-07-02 13:36:39

## Vai tro cua Codex

Ban la Codex reviewer/kien truc su project. Hay doc report ben duoi, review ky thuat, xac dinh rui ro va tao prompt/chithi tiep theo cho local worker.

## Yeu cau xu ly

1. Tom tat ngan gon worker da lam gi va ket qua hien tai.
2. Neu report da hoan thanh dung yeu cau, noi ro la da dat va khong yeu cau lam lai.
3. Neu con loi/rui ro/thieu buoc verify, neu ro muc do uu tien.
4. Viet prompt moi cho worker local, cu the ve file/module can sua, viec can lam, va cach verify.
5. Gui review/prompt vao chat Telegram de worker local tiep tuc vong lap.

## Output mong muon

Viet bang tieng Viet, ngan gon, co cac muc:

- `## Nhan dinh`
- `## Van de / Rui ro`
- `## Prompt cho worker`

## Worker Report

Báo cáo hoàn thành CODEX JOB #001 & Phân tích hệ thống tải/học video của Hermes.

# Hermes Execution Report: CODEX JOB #001 & System Analysis

- **Job ID:** telegram_job_126000
- **Status:** COMPLETED & VERIFIED (Syntax check passed)
- **Target Component:** `telegram_bot.py`
- **Report Created At:** 2026-07-02 (Local Time)

---

## 🔧 Part 1: CODEX JOB #001 Execution Details

We have refactored [telegram_bot.py](file:///c:/Work/Code/Hermes_download/hermes-agent/telegram_bot.py) to resolve event-loop blocking issues and establish a graceful shutdown process.

### 1. Fix `ask_gemini()` event loop blocking (Task 1)
- **Problem:** `ask_gemini()` performs synchronous network requests (using `google-generativeai`), blocking the main asyncio loop and freezing the bot.
- **Solution:** Wrapped all calls inside `story_command`, `review_command`, `tech_command`, and `default_chat_handler` in `asyncio.get_event_loop().run_in_executor(...)` to delegate blocking operations to a background thread pool:
```python
result = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, prompt_or_code, instruction)
```

### 2. Graceful Shutdown for `poll_outbox_loop` (Task 2)
- **Problem:** The background outbox task polled indefinitely using `while True`, which could leak threads or throw exceptions when python-telegram-bot shut down.
- **Solution:**
  - Added a global `_stop_event = asyncio.Event()` and `_outbox_task = None`.
  - Converted the outbox loop condition to `while not _stop_event.is_set():`.
  - Added a try-except block around `asyncio.sleep(4)` to catch `asyncio.CancelledError`.
  - Implemented and registered a `post_stop(application)` hook in the bot builder to trigger `_stop_event.set()` and cancel the task cleanly on exit.

### 3. Initialize Gemini Once (Task 3)
- **Problem:** `init_gemini()` was called during every single message generation, slowing down response times and repeating configuration checks.
- **Solution:** Added a `_GEMINI_INITIALIZED` flag. We now call `init_gemini()` once inside `main()` prior to launching the bot.

### 4. Verification Check
- Executed syntax validation check: `python -m py_compile telegram_bot.py`.
- **Result:** **Exit Code 0 (Success)**. The code compiles cleanly.

---

## 📊 Part 2: System Analysis (Downloading & Video Learning)

We analyzed the codebase to document the architecture of the video downloading, resource gathering, and learning features.

### 1. Video & Resource Downloading Feature
- **Core File:** [tools/video_downloader.py](file:///c:/Work/Code/Hermes_download/hermes-agent/tools/video_downloader.py) (coordinating with [tools/custom_parsers.py](file:///c:/Work/Code/Hermes_download/hermes-agent/tools/custom_parsers.py))
- **Key Mechanics:**
  - **Chinese E-Commerce Direct Download:** Automatically detects URLs from Chinese platforms (1688, Taobao, JD, Tmall, Pinduoduo). Uses `extract_ecommerce_video` to scrape direct `.mp4` URLs from the raw HTML and downloads them via standard HTTP requests for maximum speed.
  - **yt-dlp Engine:** For mainstream sites (YouTube, TikTok, Douyin, Instagram), uses the `yt-dlp` library configured with merge templates to package best video and audio streams into an `.mp4`.
  - **Cookie Sharing:** Supports passing browser cookies (`chrome`, `edge`, etc.) to bypass captchas, regional bans, or login gates.
  - **Audio Extraction:** Integrates an `FFmpeg` extraction post-processor to isolate the voiceover stream and convert it to high-quality `.mp3` format.
  - **Stream Logging:** Uses `YDLLogger` as a callback to stream raw download logs to the GUI in real time.

### 2. Video Link Learning & Analysis Pipeline
- **Core Files:** [core/job_watcher.py](file:///c:/Work/Code/Hermes_download/hermes-agent/core/job_watcher.py) and [tools/video_analyser.py](file:///c:/Work/Code/Hermes_download/hermes-agent/tools/video_analyser.py)
- **Pipeline Workflow:**
  1. **Media Resolution:** `_resolve_media_for_analysis` fetches the link, checks if it is a local file, and downloads it to a temporary `source_video/` folder in the project workspace.
  2. **Online Vision API (Gemini):**
     - Uploads the local media file using the `google.generativeai` File API.
     - Polls `uploaded_file.state.name` until status is `ACTIVE` (completes Google encoding).
     - Queries `gemini-2.5-flash` with a tailored prompt to extract hooks, timeline scripts, audio transcription, visual style, and pacing.
     - Calls `genai.delete_file()` to immediately delete the media file from Google servers on completion (ensures privacy).
  3. **Offline OpenCV Fallback:**
     - If the Gemini API key is missing or encounters a timeout error, it triggers `generate_offline_prompt()`.
     - Opens the video locally with OpenCV (`cv2.VideoCapture`) to calculate dimensions, duration, frames-per-second, average frame brightness, and average motion score.
     - Uses a Vietnamese-to-English translation mapping (`translate_action_vi_to_en`) to build descriptive video generation prompts and negative prompts for stable diffusion or video generation engines.
  4. **Proposal Structuring:**
     - **Knowledge Learning (`/hoc_kien_thuc`):** Generates structured summaries, maps tools, identifies workflow steps, and queues a review file (`knowledge_proposal.md`) to the `knowledge_base/review_queue/` for cashier/human approval.
     - **Formula Learning (`/hoc_hook_CTA`):** Extracts retention devices, hook structures, and maps visual environment elements directly to the system's re-usable prompt libraries.

