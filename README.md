# Hermes TikTok Video Factory 🎬🚀

**Hermes TikTok Video Factory** là một ứng dụng máy tính (Desktop GUI) được phát triển bằng Python và CustomTkinter, hỗ trợ các nhà sáng tạo nội dung sản xuất video đánh giá sản phẩm (Product Review) tự động, tối ưu thuật toán giữ chân của TikTok.

---

## 🛠 Cấu trúc thư mục dự án

```text
hermes-agent/
├── core/
│   ├── file_manager.py        # Các tiện ích tệp tin, chuẩn hóa tên file & folder slug
│   ├── project_manager.py     # Quản lý dự án, lưu trữ dữ liệu vào metadata.json
│   ├── keyword_generator.py   # AI sinh từ khóa tìm kiếm (Việt, Anh, Trung) qua Gemini
│   ├── script_generator.py    # AI soạn kịch bản ngắn, caption & hashtags qua Gemini
│   └── metadata_store.py      # Định nghĩa lược đồ dữ liệu dự án
├── downloaders/
│   ├── direct_downloader.py   # Công cụ tải file trực tiếp chất lượng cao qua HTTP
│   └── ytdlp_downloader.py    # Bộ tải video đa nguồn (TikTok, Douyin, YouTube...) qua yt-dlp
├── providers/
│   ├── pexels_provider.py     # Tìm kiếm & tải phôi video dọc từ Pexels API
│   ├── pixabay_provider.py    # Tìm kiếm & tải phôi video từ Pixabay API
│   ├── supplier_feed_provider.py # Đọc file feed CSV/JSON của nhà cung cấp để tải phôi
│   ├── url_list_provider.py   # Tải phôi theo danh sách URL dán thủ công
│   └── custom_scraper_adapter.py # Mẫu tích hợp trình cào video tùy chỉnh
├── editor/
│   ├── clip_analyzer.py       # Phân tích chất lượng clip dùng OpenCV (độ sáng, nét, chuyển động...)
│   ├── clip_cutter.py         # Cắt nhỏ phôi gốc thành các đoạn ngắn vertical 9:16 dùng MoviePy
│   ├── audio_helper.py        # Đo đạc thông số tệp âm thanh thuyết minh
│   ├── subtitle_generator.py  # Ghép khớp phụ đề chữ tự động dùng Pillow (không cần ImageMagick)
│   └── video_editor.py        # Dựng video tự động ghép nối các clip dọc đã chấm điểm tốt/ổn
├── gui/
│   ├── app.py                 # Thiết kế giao diện chính (9 Tabs, xử lý nền đa luồng Threaded)
│   └── components.py          # Tiện ích GUI (Console logs, Labeled Inputs, đèn check hệ thống)
├── scratch/                   # Các script kiểm thử kiểm tra chất lượng tại local
├── projects/                  # Thư mục chứa các dự án sản phẩm của bạn (Tự động tạo)
│   └── {product_slug}/
│       ├── materials/         # Phôi video gốc tải về
│       ├── clips/             # Các clip dọc ngắn 2s đã cắt ra và chấm điểm
│       ├── audio/             # Âm thanh thuyết minh (voice.mp3)
│       ├── scripts/           # Tệp kịch bản text
│       ├── storyboard/        # Bản phân cảnh & prompts sinh AI (storyboard.md, image_prompts.txt...)
│       └── exports/           # Video thành phẩm xuất ra
├── .env.example               # Tệp tin cấu hình mẫu
├── .env                       # Tệp tin cấu hình thực tế
├── requirements.txt           # Danh sách các thư viện Python
└── main_gui.py                # Điểm khởi chạy giao diện ứng dụng chính
```

---

## Job Manifest Architecture

Hermes Agent now supports a manifest-first workflow:

```text
Telegram / GUI
    -> Job Manifest
    -> Planner
    -> Task Queue
    -> Worker Runner
    -> Artifact Store
    -> GUI Monitor / Telegram Reply
```

Runtime job data is stored under `jobs/{pending,running,done,failed}/{job_id}`:

- `manifest.json`: normalized job contract.
- `tasks/task_XXX.json`: task status and output target.
- `tasks/task_XXX_worker_prompt.md`: manual Codex/Antigravity prompt for one task.
- `worker_prompt.md`: master prompt/checklist for the whole job.
- `artifacts/`: output files such as `analysis.md`, `product_lock.md`, `storyboard.md`, `video_prompts.md`, `workflow.json`.
- `logs/`: worker/system logs.

Telegram and GUI create manifests only. The Planner expands each manifest by engine (`ai_studio`, `html_video`, `mixed`, `capcut`). The worker runner can claim the next task locally without calling paid model APIs; Codex/Antigravity can manually read the task prompt and write the requested artifact. The GUI auto-refreshes task progress and artifact buttons.

User flow guide: `docs/hermes-user-flow.md`

---

## 📋 Yêu cầu hệ thống

1. **Python 3.10+**
2. **FFmpeg** (Đã được liên kết trực tiếp trong `.env`).
3. **Google Gemini API Key** (Dùng sinh kịch bản & từ khóa).
4. **OpenCV** (Dùng phân tích chất lượng video tại local).

---

## 🚀 Hướng dẫn cài đặt và sử dụng

### Bước 1: Mở Terminal tại thư mục dự án
```powershell
cd c:\Work\Code\Hermes_download\hermes-agent
```

### Bước 2: Cài đặt thư viện phụ thuộc
```powershell
pip install -r requirements.txt
```

### Bước 3: Khởi chạy ứng dụng GUI
```powershell
$env:PYTHONUTF8=1
python main_gui.py
```

---

## 💡 Quy trình sản xuất video & thiết kế ý tưởng trong App

1. **Tab 1: Sản phẩm**: Nhập tên sản phẩm và các chi tiết bán hàng. Bấm **Khởi Tạo & Lưu Dự Án Mới** để tạo cấu trúc thư mục lưu trữ tại `projects/{product_slug}/`.
2. **Tab 2: Tìm phôi**: Click **Tạo từ khóa tìm kiếm (AI Gemini)** để sinh từ khóa. Chọn các nguồn tải rồi bấm **Bắt Đầu Tải Phôi** để lưu phôi gốc vào `materials/`.
3. **Tab 3: Cắt clip phôi**: Cấu hình các thông số cắt (độ dài, bỏ qua đầu video). Bấm **Bắt Đầu Cắt Clip Phôi** để tự động xuất các clip dọc 9:16 (720x1280) vào `clips/` kèm phân tích chất lượng bằng OpenCV.
4. **Tab 4: Kịch bản**: Chọn phong cách hook mong muốn và bấm **Viết kịch bản mới (AI Gemini)**. Sau đó click **Sao chép kịch bản**.
5. **Tab 5: Audio**: Dán kịch bản thuyết minh vào ElevenLabs để tạo giọng đọc, tải tệp `.mp3` về, rồi bấm **Chọn & Import File MP3** ở tab này để nạp nhạc.
6. **Tab 6: Dựng video**: Tích chọn **Bật phụ đề chữ** và bấm **Bắt Đầu Dựng Video TikTok (9:16)**. Hệ thống sẽ ưu tiên chọn các clip có điểm chất lượng "Good", sau đó là "Okay" từ thư mục `clips/` để ghép nối khớp chính xác thời lượng tiếng thuyết minh.
7. **Tab 7: Kết quả**: Click **Mở Thư Mục Chứa Video** để lấy thành phẩm `final_video.mp4` đã được crop dọc 9:16 chuẩn TikTok và copy caption gợi ý kèm hashtag để đăng bài.
8. **Tab 8: Storyboard AI**: Sinh kịch bản phân cảnh chi tiết cùng các prompt hình ảnh/video (English/Vietnamese) chuyên nghiệp được tối ưu hóa cho tỷ lệ 9:16 để dán trực tiếp vào ChatGPT, Midjourney, Veo, Luma...

---

## 🔍 Cắt clip phôi và phân tích chất lượng (Local OpenCV Analysis)

Tính năng cắt clip phôi và phân tích chất lượng chạy **hoàn toàn local, miễn phí và ngoại tuyến**, không sử dụng Gemini API hay các dịch vụ AI trả phí khác. Tính năng này hoạt động dựa trên các thư viện xử lý hình ảnh **OpenCV** và **MoviePy**:

1. **Cắt Clip Tự Động (MoviePy)**: Cắt phôi gốc thành các đoạn ngắn liên tiếp (mặc định 2.0 giây) sau khi bỏ qua phần giới thiệu (mặc định 1.0 giây). Xuất video định dạng H.264 dọc 9:16 (720x1280) tĩnh âm thanh.
2. **Chấm Điểm Chất Lượng OpenCV**:
   - **Độ sáng (Brightness - 25% trọng số)**: Đo lường độ sáng trung bình của khung hình. Điểm cao nhất ở mức sáng lý tưởng (130). Clip quá tối hoặc bị cháy sáng (overexposed) nhận điểm thấp hơn.
   - **Chuyển động (Motion - 30% trọng số)**: Tính toán sự khác biệt điểm ảnh giữa các khung hình liên tiếp để phát hiện chuyển động. Tránh các clip tĩnh như ảnh chụp và lọc nhiễu ngẫu nhiên.
   - **Độ nét (Sharpness - 25% trọng số)**: Sử dụng phương sai bộ lọc Laplacian trên khung hình chuẩn hóa kích thước 512x512 để phát hiện tiêu cự. Các clip mờ, nhòe sẽ nhận điểm thấp.
   - **Sự tương thích dọc (Vertical Score - 20% trọng số)**: Đánh giá dựa trên tỉ lệ khung hình (aspect ratio) của **video phôi gốc** trước khi crop. Phôi gốc dọc (9:16) nhận 100 điểm, phôi vuông (1:1) nhận 60 điểm, phôi ngang (16:9) nhận 40 điểm (do mất nhiều chi tiết khi crop).
   - **Thay đổi bối cảnh (Scene Change)**: Tính toán sự tương đồng biểu đồ màu giữa các khung hình. Các clip tĩnh không có thay đổi bối cảnh nhận điểm thấp, giúp nhận diện độ sinh động của góc quay.
3. **Phân Loại Khuyên Dùng**:
   - Điểm tổng hợp `>= 70`: Xếp hạng **Good** (Tốt).
   - Điểm tổng hợp `>= 45`: Xếp hạng **Okay** (Tạm ổn).
   - Điểm tổng hợp `< 45`: Xếp hạng **Reject** (Bị loại).
4. **Loại Bỏ Tự Động**: Nếu bật tùy chọn "Bỏ clip kém chất lượng", các clip bị xếp hạng **Reject** sẽ bị tự động xóa khỏi đĩa để tiết kiệm bộ nhớ, nhưng hồ sơ chấm điểm vẫn được ghi nhận trong `metadata.json` với trạng thái `"Rejected"` và `"deleted": true`.

---

## 🎨 Lên kịch bản phân cảnh và Prompts với Storyboard AI

Tính năng **Storyboard AI** (Tab 8) hỗ trợ tạo ra kịch bản phân cảnh toàn diện cho sản phẩm của bạn:
- **Tự động điền dữ liệu**: Các trường thông tin sản phẩm (Tên, Mô tả, USP, Pain points...) tự động đồng bộ từ Tab 1 khi tải dự án.
- **Tùy chỉnh định hướng**: Tự do điều chỉnh phong cách video, thời lượng, số lượng phân cảnh mong muốn và ghi chú đặc biệt cho hình ảnh/background.
- **Target Prompt**: Lựa chọn công cụ AI đích (như Google Labs / Veo, ChatGPT, Gemini...) để định hình phong cách viết prompt tương thích tốt nhất.
- **Bộ Prompts Chuyên Nghiệp**: Mỗi phân cảnh được sinh kèm prompt hình ảnh & prompt video bằng tiếng Anh chi tiết, chứa sẵn các tham số tối ưu tỉ lệ dọc (`vertical 9:16 aspect ratio`), phong cách review TikTok (`TikTok product review video style`), góc quay và chuyển động mượt mà.
- **Quản lý xuất tệp tin**:
  - Tự động lưu 4 file: `storyboard.json` (dữ liệu cấu trúc), `storyboard.md` (bản xem trước đẹp mắt), `image_prompts.txt` (danh sách prompt ảnh), `video_prompts.txt` (danh sách prompt video).
  - Đường dẫn lưu: Nếu có dự án đang mở, lưu tại `projects/{product_slug}/storyboard/`. Nếu chưa tạo dự án, lưu tại `storyboard_reports/{storyboard_slug}/`.
  - Hỗ trợ nút **Mở thư mục** trực tiếp và các nút **Copy nhanh** (Copy toàn bộ kịch bản, prompt ảnh, prompt video) để dán sang các công cụ AI khác vô cùng tiện lợi.
---

## AI Video Providers

Tab **Tìm phôi** có thêm nguồn **Tạo phôi bằng AI Video** để tạo prompt/video theo các keyword hiện có của dự án.

- Nếu provider chưa có API key hoặc endpoint ổn định, app sẽ lưu file `ai_video_prompts_*.txt` trong thư mục `Phoi/` để bạn copy sang Grok, Pika, Krea, Leonardo.Ai hoặc Runway dùng thủ công.
- Nếu bạn cấu hình đủ `*_API_KEY` và `*_VIDEO_ENDPOINT` trong `.env`, app sẽ gọi API, lấy URL video trả về và tải file `.mp4` vào thư mục `Phoi/`.
- Provider **Custom API** dùng `AI_VIDEO_CUSTOM_API_KEY` và `AI_VIDEO_CUSTOM_ENDPOINT`, phù hợp khi bạn có proxy/API riêng. Payload gửi đi gồm `model`, `prompt`, `duration`, `aspect_ratio`, `ratio`, `resolution`.

Các biến cấu hình mẫu nằm trong `.env.example`.

## Telegram Video Intake

Bot Telegram có thể nhận link video rồi hỏi bạn muốn xử lý theo hướng nào:

```text
<gửi link TikTok/YouTube/Shorts>
```

Bot sẽ hỏi chọn:

```text
/hoc_video
/len_kich_ban
```

- `/hoc_video`: tóm tắt nội dung video, rút hook/body/CTA, mô tả môi trường/sản phẩm/lời nói, rồi map bài học vào promptA/promptB/promptC hoặc đề xuất prompt mới.
- `/len_kich_ban`: phân tích video rồi tạo kịch bản mới gồm môi trường, sản phẩm, lời nói, hook, CTA, scene breakdown, voiceover, image prompts, video prompts và CapCut notes.

Bạn cũng có thể gửi trực tiếp:

```text
/hoc_video https://...
/len_kich_ban https://...
```

Bot sẽ tạo job trong `.agent_jobs/inbox` và sinh worker prompt tại `projects/{project_slug}/agent_outputs/{job_id}/antigravity_codex_prompt.md` để Codex/Antigravity xử lý tiếp.


---

## New machine (Hermes Personal)

This repository contains the Hermes runtime source used by Hermes Personal.
A separate installation/clone of NousResearch Hermes is NOT required.

```
git clone <this repo>
cd hermes-agent
.\setup.ps1
# edit .env / configure external credentials if doctor requests them
.\start.ps1
```

Update:

```
git pull
.\setup.ps1
.\start.ps1
```

`setup.ps1`:
- checks Python / uv / Node / FFmpeg
- creates/reuses `<repo>\.venv` and installs THIS repo editable
- installs web/ dependencies
- copies `.env.example` → `.env` only if missing (never overwrites)
- creates the sibling `<checkout-parent>\hermes-agent-data` data root
- normalizes repo-local MCP commands and data paths with config backups

`start.ps1`:
- verifies imports resolve from THIS repo and checks local 9Router
- starts the durable worker + aiohttp backend from THIS repo/.venv
- `-UI` also starts the React dev server
- invokes THIS repo's `.venv\Scripts\hermes.exe`

Verify (no paid calls):

```
.\.venv\Scripts\python.exe scripts\doctor.py
```

External dependencies (not bundled): Google Cloud / Vertex credentials, local 9Router endpoint, FFmpeg. Fake providers are test-only and require `HERMES_ALLOW_FAKE_PROVIDERS=1`.
