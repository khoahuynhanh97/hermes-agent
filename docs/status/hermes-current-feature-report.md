# Hermes Current Feature Report

> Tài liệu trạng thái chuẩn để đọc trước mỗi lần nâng cấp Hermes.
> Cập nhật gần nhất: **2026-07-16 00:47 ICT (UTC+07:00)**.

## 1. Cách dùng tài liệu này

- Đọc file này trước khi lập kế hoạch hoặc sửa code.
- Kiểm tra lại runtime và dữ liệu bằng các lệnh ở mục 13; không giả định snapshot cũ vẫn đúng.
- Sau mỗi đợt nâng cấp, cập nhật ngày kiểm tra, bảng tính năng, giới hạn, kết quả test và changelog ở cuối file.
- Không ghi API key, Telegram token, user ID hoặc dữ liệu nhạy cảm vào tài liệu.
- SQLite trên laptop 1 là source of truth. Google Drive chỉ dùng backup/export/restore.

### Quy ước trạng thái

| Trạng thái | Ý nghĩa |
|---|---|
| **ACTIVE** | Đang chạy và đã kiểm tra runtime thực tế. |
| **COMPLETE** | Đã implement và có test, nhưng không nhất thiết đang có dữ liệu thực tế. |
| **PARTIAL** | Dùng được trong một số điều kiện; còn fallback hoặc dependency chưa sẵn sàng. |
| **LEGACY** | Code cũ còn tồn tại để tương thích, không phải hướng phát triển chính. |
| **DEFERRED** | Chủ động hoãn vì chưa cần cho trợ lý cá nhân. |
| **NOT VERIFIED** | Có code nhưng chưa được kiểm tra live trong snapshot này. |

## 2. Định nghĩa sản phẩm hiện tại

Hermes là **trợ lý AI cá nhân qua Telegram**, tập trung vào:

1. Chat và hỏi đáp bằng ngôn ngữ tự nhiên.
2. Học từ text, URL, TikTok/YouTube và file người dùng gửi.
3. Tóm tắt nguồn ngay cho người dùng và tạo lesson có cấu trúc.
4. Chỉ dùng knowledge/memory đã được duyệt cho câu trả lời tương lai.
5. Tìm repository GitHub khi knowledge đã duyệt không đủ hoặc người dùng yêu cầu tìm mới.
6. Dùng 9Router cho text LLM và Gemini trực tiếp chỉ cho vision/media.

Video generation, batch production và publishing **không phải scope chính hiện tại**.

## 3. Kiến trúc runtime

```text
Telegram user
    -> telegram_bot.py
    -> Hermes personal assistant / command router
       -> approved knowledge + approved memory + bounded conversation
       -> 9Router (text LLM, localhost only)
       -> GitHub repository search khi cần
       -> SQLite job queue cho tác vụ dài
            -> scripts/run_job_worker.py
            -> ingestion + transcript/media/document analysis
            -> structured pending lessons
            -> Telegram summary + approval commands

Primary data: D:\HermesData\hermes.db
Artifacts:    D:\work\hermes-agent\projects và D:\HermesData
Backup:       G:\My Drive\Hermes Knowledge Base\backups
```

## 4. Snapshot runtime đã xác minh

| Thành phần | Trạng thái | Kết quả ngày 2026-07-16 |
|---|---|---|
| Telegram bot | **ACTIVE** | `telegram_bot.py` đang chạy; log có `Application started`; không có ERROR/Traceback. |
| Job worker | **ACTIVE** | `scripts/run_job_worker.py` đang poll mỗi 3 giây; không có ERROR/Traceback. |
| 9Router | **ACTIVE** | Health HTTP 200; chỉ listen `127.0.0.1:20128`; completion smoke trả `OK`. |
| SQLite | **ACTIVE** | `PRAGMA quick_check=ok`. |
| Knowledge | **ACTIVE** | 26 lesson: 21 approved, 5 pending, 0 rejected, 0 cần re-analysis. |
| Knowledge search | **ACTIVE** | 21 approved lesson có trong FTS5; pending không được index để retrieval. |
| Jobs | **ACTIVE** | 3 completed; 0 queued/running/failed/cancelled. |
| Evidence | **ACTIVE** | 9 evidence records. |
| Messages | **COMPLETE** | Schema/repository có sẵn; hiện có 0 message trong SQLite. |
| Durable memory | **COMPLETE** | Lifecycle có sẵn; hiện có 0 memory thực tế. |
| Google Drive backup | **ACTIVE** | Backup mới nhất verify `ok`; không còn file WAL/SHM phụ. |
| TikTok crawler | **ACTIVE** | Local API V4.1.2 listen `127.0.0.1:5556`; OpenAPI contract đúng; structured HTML fallback đã tải thật 6 ảnh. |
| Local transcription | **ACTIVE** | FFmpeg/ffprobe 8.1.2 và faster-whisper `base` CPU/int8; TikTok smoke tạo transcript tiếng Việt 4.434 ký tự. |
| Test suite | **ACTIVE** | 74 test chạy thành công. |
| Git worktree | **PARTIAL** | Branch `codex/hermes-personal-assistant-core`; 93 path đang dirty, gồm 26 tracked và 67 untracked. |

Commit nền hiện tại: `55702354b` (`docs: specify JSON reanalysis workflow`). Snapshot thực tế còn nhiều thay đổi chưa commit, vì vậy commit này **không đại diện đầy đủ code đang chạy**.

## 5. Bảng tính năng trợ lý cá nhân

| Nhóm | Tính năng | Trạng thái | Ghi chú thực tế |
|---|---|---|---|
| Telegram | Chat tự nhiên | **ACTIVE** | Tin nhắn thường được định tuyến sang trợ lý và 9Router. |
| Telegram | HTML formatting | **COMPLETE** | Response text đi qua helper HTML, có fallback plain text khi Telegram từ chối HTML. |
| Telegram | Chia nhỏ message dài | **COMPLETE** | Có helper gửi theo chunk để tránh giới hạn Telegram. |
| Telegram | Authorization | **ACTIVE** | Allowlist `TELEGRAM_ALLOWED_USER_IDS`; mặc định fail closed. |
| Telegram | Text, link và attachment | **ACTIVE** | Nhận video, audio, voice, photo và document được cho phép. |
| Telegram | Inline callback buttons | **PARTIAL** | Handler còn tồn tại, nhưng chưa live-test lại; slash command là đường duyệt đáng tin cậy. |
| Assistant | Knowledge-first answer | **COMPLETE** | Tìm approved knowledge trước; pending/rejected không được dùng. |
| Assistant | Chat context ngắn hạn | **COMPLETE** | Giới hạn 12 message/12.000 ký tự; chưa có dữ liệu live trong SQLite. |
| Assistant | Memory dài hạn | **COMPLETE** | Pending/approved/rejected/deactivated; chỉ approved được đưa vào prompt. |
| Assistant | Nhận diện yêu cầu học tự nhiên | **COMPLETE** | Hỗ trợ câu như `Hãy học kiến thức này: ...`. |
| Assistant | Nhận diện yêu cầu nhớ tự nhiên | **COMPLETE** | Hỗ trợ câu như `Hãy nhớ: ...`; tạo memory pending. |
| Assistant | Code/tech routing | **PARTIAL** | Có heuristic code và command riêng; không phải code-agent hoàn chỉnh. |
| External search | GitHub repository search | **COMPLETE** | Dùng GitHub Search API, tối đa 5 repo, có timeout và đánh dấu dữ liệu untrusted; chưa live-test API trong snapshot này. |
| External search | Generic web search | **DEFERRED** | Chưa có search engine tổng quát; chỉ inspect URL được gửi và GitHub repo search. |

## 6. Bảng tính năng học và ingestion

| Nguồn | Trạng thái | Cách xử lý | Giới hạn/điều kiện |
|---|---|---|---|
| Plain text/note | **ACTIVE** | Phân tích bằng LLM, tạo source/evidence/lesson pending. | Cần nội dung đủ làm evidence. |
| Website URL | **COMPLETE** | SSRF validation, tối đa 3 redirect, 2 MB, trích tối đa 50.000 ký tự HTML/text/JSON. | Không chạy JavaScript browser; trang động có thể thiếu nội dung. |
| YouTube video | **PARTIAL** | yt-dlp caption -> audio/Whisper -> media/vision -> metadata fallback. | Runtime local đã có FFmpeg/ffprobe và faster-whisper; nguồn bên ngoài vẫn có thể chặn download. |
| TikTok video | **PARTIAL** | yt-dlp tải video; Gemini vision hoặc transcript; video tạm được dọn sau phân tích. | Download đã chạy thực tế; Gemini SDK mới chưa live-test media thật. TikTok có thể thay đổi và yêu cầu upload nguồn. |
| TikTok photo carousel | **ACTIVE** | Repo local là tầng 1; structured `api-data` HTML là tầng 2; tải tối đa 20 ảnh/50 MB rồi vision. | Live smoke tải và decode 6 ảnh. Upstream App API có thể 429; metadata-only vẫn không tạo lesson. |
| Telegram image/photo | **PARTIAL** | File được nhận và đưa vào learning flow/vision. | Gemini API đã cấu hình; SDK mới chưa live-test với media thật trong snapshot này. |
| Audio/voice | **ACTIVE** | Nhận file hoặc audio từ URL; faster-whisper `base` CPU/int8; model cache trên ổ D. | Live smoke WAV và TikTok đều trả transcript; file không có lời có thể trả `no_speech_detected`. |
| TXT/MD/JSON/CSV/SRT/VTT | **COMPLETE** | Đọc UTF-8 local, giới hạn mặc định 2 MB. | File lớn hơn bị bỏ qua. |
| PDF | **COMPLETE** | Trích text local bằng `pypdf`. | Chỉ PDF có text; PDF scan cần vision/OCR. Giới hạn mặc định 2 MB. |
| DOCX | **COMPLETE** | Trích paragraph và table bằng `python-docx`. | Giới hạn mặc định 2 MB. |
| Video upload | **PARTIAL** | Gemini vision; nếu thất bại dùng transcript khi có. | Không giả lập lesson khi không có source-bound evidence. |

### Fallback và độ tin cậy

| Hành vi | Trạng thái | Quy tắc |
|---|---|---|
| Transcript/caption fallback | **COMPLETE** | Transcript được coi là untrusted reference; confidence thường `medium`. |
| Video + transcript | **COMPLETE** | Evidence đầy đủ hơn; confidence `high`. |
| Metadata-only | **COMPLETE** | Confidence `low`; không tạo reusable lesson chỉ dựa vào metadata. |
| Không có nguồn đủ tin cậy | **COMPLETE** | Trả `needs_source` và yêu cầu gửi lại link/file/transcript. |
| JSON malformed | **COMPLETE** | Gọi thêm một lượt LLM để normalize JSON. |
| Raw analysis recovery | **COMPLETE** | Chỉ cho phép `/recover` hoặc `/re_analysis` khi raw analysis đủ tin cậy. |
| Prompt injection trong nguồn | **PARTIAL** | Transcript/metadata được bao untrusted; có keyword guard và audit. Đây không phải sandbox tuyệt đối. |

## 7. Knowledge và approval lifecycle

| Tính năng | Trạng thái | Ghi chú |
|---|---|---|
| SQLite source of truth | **ACTIVE** | `HERMES_STORAGE_BACKEND=sqlite`; DB tại `D:\HermesData\hermes.db`. |
| Source deduplication | **COMPLETE** | Unique theo owner + source key; lesson có dedupe cơ bản. |
| Structured lesson | **COMPLETE** | Title, summary, content, type/category, tags, key lessons, confidence, evidence và detail JSON. |
| Pending/approved/rejected | **ACTIVE** | Có event history; hiện 21 approved và 5 pending. |
| Approved-only retrieval | **COMPLETE** | FTS chỉ chứa approved lesson; `needs_reanalysis` không thể approve. |
| Approve từng lesson | **ACTIVE** | `/approve <id hoặc số thứ tự>`. |
| Reject từng lesson | **ACTIVE** | `/reject <id hoặc số thứ tự>`. |
| Approve theo source | **COMPLETE** | `/approve_source <lesson_id>`; bỏ qua lesson cần re-analysis. |
| Approve tất cả đang hiển thị | **ACTIVE** | `/approve_all`. |
| Re-analysis | **COMPLETE** | `/re_analysis <lesson_id>`. |
| Knowledge display | **ACTIVE** | HTML, nhóm category, title đậm, summary ngắn và slash actions. |
| Legacy JSON store | **LEGACY** | Còn để migration/compatibility; không phải transactional source khi SQLite bật. |
| Artifact registry | **PARTIAL** | Bảng `artifacts` có schema nhưng hiện 0 record; file thực vẫn nằm trong project/job directories. |

## 8. Jobs và worker

| Tính năng | Trạng thái | Ghi chú |
|---|---|---|
| SQLite queue | **ACTIVE** | Một local worker; atomic claim bằng transaction. |
| States | **COMPLETE** | `queued`, `running`, `completed`, `failed`, `cancelled`. |
| `/status` và `/jobs` | **ACTIVE** | Xem trạng thái job thuộc owner. |
| `/retry` | **COMPLETE** | Chỉ retry failed job, giới hạn attempt. |
| `/cancel` | **COMPLETE** | Cancel queued; running dùng cooperative cancellation. |
| Restart recovery | **COMPLETE** | Running job bị gián đoạn được requeue hoặc cancel theo flag. |
| Timeout/retry model | **COMPLETE** | Gateway có request timeout và retry giới hạn. |
| Job retention | **PARTIAL** | Có `prune_terminal()` nhưng chưa được gọi định kỳ. |
| Distributed queue | **DEFERRED** | Không dùng Celery/Redis/RabbitMQ; không cần cho một người dùng. |

## 9. LLM, model routing và tools

| Thành phần | Trạng thái | Cấu hình/giới hạn |
|---|---|---|
| 9Router text gateway | **ACTIVE** | OpenAI-compatible tại `http://127.0.0.1:20128/v1`. |
| Chat model | **ACTIVE** | `kr/glm-5`. |
| Learning/deep analysis model | **ACTIVE** | `kr/glm-5`. |
| Code model | **COMPLETE** | `kr/qwen3-coder-next`; model tồn tại trong 9Router. |
| Rule-based task routing | **COMPLETE** | Chat/summarize -> chat alias; learning/analysis/structured -> learning alias; code -> code alias. |
| Legacy model fallback | **COMPLETE** | Tắt mặc định (`LLM_ENABLE_LEGACY_PROVIDER_FALLBACK=0`). |
| Structured JSON validation | **COMPLETE** | Parse/validate schema và bounded re-normalization. |
| Vision model | **PARTIAL** | Dedicated Gemini adapter dùng `google-genai 2.11.0`; chưa đi qua 9Router. |
| Tool registry | **PARTIAL** | Manifest validation và shell-free Python execution có timeout; hiện chỉ có 2 manifest nội bộ. |
| Arbitrary shell | **COMPLETE** | Registry không dùng shell và chỉ chạy generated Python tools trong thư mục cho phép. |

## 10. Commands hiện có

### Commands chính nên dùng

| Nhu cầu | Commands |
|---|---|
| Học kiến thức | `/learn`, `/hoc_kien_thuc`, hoặc chat `Hãy học kiến thức này: ...` |
| Xem knowledge | `/knowledge`, `/knowledge pending`, `/knowledge approved`, `/knowledge rejected` |
| Duyệt knowledge | `/approve`, `/reject`, `/approve_source`, `/approve_all` |
| Phân tích lại/phục hồi | `/re_analysis`, `/recover` |
| Jobs | `/status`, `/jobs`, `/retry`, `/cancel`, `/report` |
| Memory | `/remember`, `/memory`, `/approve_memory`, `/reject_memory`, `/clear_memory` |
| Tìm repo | `/tim_repo` hoặc chat tự nhiên có từ khóa repo/GitHub |
| Cấu hình/trợ giúp | `/start`, `/help`, `/settings` |

### Commands phụ hoặc legacy

`/story`, `/review`, `/tech`, `/local`, `/hoc_video`, `/hoc_hook_CTA`,
`/len_kich_ban`, `/luu_prompt`, `/de_xuat_nang_cap`, `/assistant`,
`/code_plan`, `/htmlvideo`.

Các command này còn hoạt động để tương thích nhưng không phải ưu tiên của Hermes Personal Assistant.

## 11. Phần legacy và phần chủ động hoãn

| Thành phần | Trạng thái | Quyết định |
|---|---|---|
| `main_gui.py` / TikTok Video Factory GUI | **LEGACY** | Không phải runtime chính; không được test trong bộ 57 test hiện tại. |
| Script/story/video planning | **LEGACY** | Giữ tương thích; chỉ sửa khi ảnh hưởng trợ lý hoặc người dùng cần thực tế. |
| FFmpeg composition | **DEFERRED** | FFmpeg đã cài cho ingestion/transcription; tính năng dựng video vẫn chủ động hoãn. |
| AI video providers | **DEFERRED** | Không tích hợp paid provider hoặc batch generation. |
| Auto publishing | **DEFERRED** | Không publish TikTok tự động. |
| Vector database | **DEFERRED** | FTS5 đủ cho dữ liệu cá nhân hiện tại. |
| Multi-agent/workflow engine | **DEFERRED** | Không cần; giữ một assistant orchestrator và một worker. |
| Active-active laptop sync | **DEFERRED** | Laptop 1 active; laptop 2 chỉ restore/failover thủ công. |

## 12. Known issues và ưu tiên nâng cấp

| Ưu tiên | Vấn đề | Hành động nhỏ nhất hợp lý |
|---|---|---|
| **P1** | Worktree có 93 path chưa commit; code chạy không được bảo vệ đầy đủ bởi Git. | Phân loại thay đổi user/runtime, bỏ file generated khỏi Git, rồi tạo commit có chủ đích. |
| **P2** | Upstream TikTok App API có thể trả HTTP 429 khi không có cookie hợp lệ. | Giữ structured HTML fallback; chỉ cấu hình cookie local trong crawler khi fallback không lấy được dữ liệu. |
| **P2** | Vision SDK mới chưa live-test media thật. | Gửi một ảnh và một video nhỏ qua Telegram, kiểm tra Gemini upload/generate/delete. |
| **P2** | Backup chỉ chạy thủ công. | Khi cần, thêm một Windows Scheduled Task gọi `scripts/hermes_backup.py backup`. |
| **P3** | `artifacts` table chưa được dùng để index file thực. | Chỉ nối artifact persistence khi retrieval/source audit cần tới file. |
| **P3** | Job retention chưa tự chạy. | Gọi prune định kỳ hoặc từ backup script khi storage bắt đầu tăng. |
| **P3** | Memory code chưa có dữ liệu live. | Test một vòng `/remember` -> approve -> chat retrieval trước khi mở rộng memory. |

Không nên thêm microservices, Redis, Celery, vector DB, plugin framework hoặc video production engine ở giai đoạn này.

## 13. Lệnh vận hành và kiểm tra chuẩn

```powershell
cd D:\work\hermes-agent

# Start 9Router chỉ trên localhost
.\scripts\start_9router_local.ps1 -Background

# Start optional TikTok Photo Mode crawler chỉ trên localhost
.\scripts\start_tiktok_crawler_local.ps1

# Start bot và worker ở hai terminal riêng
.\.venv\Scripts\python.exe telegram_bot.py
.\.venv\Scripts\python.exe scripts\run_job_worker.py

# Test
.\.venv\Scripts\python.exe -m unittest discover -s tests\hermes
.\.venv\Scripts\python.exe -m compileall -q hermes core tools telegram_bot.py scripts tests\hermes
.\.venv\Scripts\python.exe -m pip check
git diff --check

# Backup/export/verify
.\.venv\Scripts\python.exe scripts\hermes_backup.py backup
.\.venv\Scripts\python.exe scripts\hermes_backup.py export
.\.venv\Scripts\python.exe scripts\hermes_backup.py verify "<backup.db>"
```

## 14. File quan trọng cần đọc trước khi nâng cấp

| Mục đích | File |
|---|---|
| Telegram adapter và commands | `telegram_bot.py` |
| Worker learning runtime | `core/job_watcher.py` |
| Job adapter hiện tại | `core/agent_jobs.py` |
| Text LLM gateway/9Router | `core/llm_gateway.py` |
| Model capability wrapper | `hermes/llm.py` |
| SQLite schema | `hermes/db.py` |
| Knowledge repository/FTS | `hermes/knowledge.py` |
| Learning result persistence | `hermes/learning.py` |
| Memory repository | `hermes/memory.py` |
| Job repository | `hermes/jobs.py` |
| Assistant context routing | `hermes/assistant.py` |
| Backup/restore | `hermes/backup.py` |
| Video/image vision | `tools/video_analyser.py` |
| TikTok photo resolver | `tools/tiktok_media_resolver.py` |
| Generic URL ingestion | `tools/url_inspector.py` |
| Security URL validation | `core/source_validation.py` |
| Tests | `tests/hermes/` |
| Backup runbook | `docs/runbooks/hermes-sqlite-backup-restore.md` |
| Cutover runbook | `docs/runbooks/hermes-sqlite-cutover.md` |
| TikTok crawler runbook | `docs/runbooks/tiktok-crawler-local.md` |
| Local transcription runbook | `docs/runbooks/local-transcription.md` |

## 15. Checklist cập nhật tài liệu sau mỗi upgrade

- [ ] Cập nhật thời gian kiểm tra và commit/branch.
- [ ] Chạy test và ghi số lượng pass/fail thực tế.
- [ ] Kiểm tra bot, worker, 9Router listener/health và log errors.
- [ ] Chạy SQLite `quick_check`; cập nhật counts knowledge/jobs/memory.
- [ ] Verify backup mới nhất.
- [ ] Cập nhật status của feature đã sửa.
- [ ] Bổ sung hoặc xóa known issue, không chỉ thêm issue mới.
- [ ] Cập nhật command nếu UX Telegram thay đổi.
- [ ] Không đánh dấu ACTIVE nếu chỉ có unit test mà chưa kiểm tra runtime.

## 16. Changelog của tài liệu

| Ngày | Thay đổi |
|---|---|
| 2026-07-16 | Tạo snapshot đầu tiên sau SQLite cutover, 9Router localhost hardening, PDF/DOCX ingestion, `google-genai` migration và backup sidecar cleanup. |
| 2026-07-16 | Cài crawler TikTok V4.1.2, FFmpeg/ffprobe 8.1.2, faster-whisper; thêm HTML Photo Mode fallback, image validation và yt-dlp impersonation. |
