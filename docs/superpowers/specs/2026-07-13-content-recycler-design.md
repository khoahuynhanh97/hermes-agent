# Design Spec: Quy trình Tự động hóa Tái chế Nội dung Video (Content Recycler Pipeline)

Ngày tạo: 2026-07-13
Mục tiêu: Nâng cấp dự án Hermes TikTok Video Factory với quy trình module hóa (Modular Pipeline) cho phép tự động cào video/lời thoại, biên tập kịch bản AI, cào phôi hình ảnh tự động, dựng video nội dung kiến thức/review hoàn chỉnh (9:16 dọc hoặc 16:9 ngang), và hỗ trợ xuất bản lên mạng xã hội (Facebook/TikTok).

---

## 1. Yêu cầu & Phạm vi (Requirements & Scope)

### Mục tiêu cốt lõi:
- **Cào và Phân tích Nguồn (Module 1):** Tải video gốc từ TikTok, YouTube, Facebook, trích xuất lời thoại (transcript) bằng VTT hoặc OpenAI Whisper.
- **Biên kịch lại bằng AI (Module 2):** Dựng kịch bản mới dựa trên lời thoại gốc dưới dạng file cấu trúc `script.json`, cho phép người dùng tùy chỉnh trước khi sinh video.
- **Quản lý & Cào Phôi Hình ảnh (Module 3):** Cào phôi ảnh từ công cụ tìm kiếm và stock media theo từ khóa kịch bản (asset pre-crawler). Khớp hình ảnh thông minh và tự động sinh ảnh AI làm fallback khi thiếu.
- **Dựng Video (Module 4):** Edge-TTS lồng tiếng tiếng Việt miễn phí, ghép ảnh/video theo từng phân cảnh (chuyển cảnh crossfade, hiệu ứng chuyển động Ken Burns pan/zoom), tự động chèn nhạc nền và phụ đề.
- **Đăng bài (Module 5):** Gửi video kèm caption/hashtag qua Telegram Bot và hỗ trợ script CLI Selenium auto-upload.
- **Tương tác GUI:** Bổ sung tab **Content Recycler** vào giao diện CustomTkinter của Hermes để quản trị quy trình trực quan.

---

## 2. Kiến trúc & Thiết kế Module (Architecture & Modules)

Hệ thống được thiết kế theo hướng **Quy trình Module Hóa (Modular Task Pipeline)** để tách biệt trách nhiệm và dễ gán lỗi (debug):

### Module 1: Source Crawler (`core/content_source.py`) [NEW]
- **Chức năng:** Tải video gốc, trích xuất transcript, phân tích cấu trúc video gốc thông qua Gemini Vision.
- **Tái sử dụng:** [tools/video_downloader.py](file:///c:/Work/Code/Hermes_download/hermes-agent/tools/video_downloader.py), [core/video_fetcher.py](file:///c:/Work/Code/Hermes_download/hermes-agent/core/video_fetcher.py), [tools/video_analyser.py](file:///c:/Work/Code/Hermes_download/hermes-agent/tools/video_analyser.py).
- **Đầu ra:** File `projects/{project_slug}/source.json`.

### Module 2: AI Script Rewriter (`core/script_generator.py`) [MODIFY]
- **Chức năng:** Bổ sung hàm `generate_recycled_script()` vào script generator hiện tại.
- **Luồng hoạt động:** Nhận đầu vào là `source.json` -> Gọi Gemini API kết hợp học phong cách từ Knowledge Store (`UnifiedKnowledgeStore`) -> Tạo kịch bản phân cảnh chi tiết.
- **Đầu ra:** File `projects/{project_slug}/scripts/script.json`.

### Module 3: Asset Pipeline & Pre-Crawler [NEW]
- **Tệp mới 1:** `core/asset_crawler.py` (Tool CLI cào ảnh Google/Pinterest/Stock theo từ khóa của chủ đề làm phôi ảnh trước).
- **Tệp mới 2:** `core/asset_pipeline.py` (Quản lý khớp phôi ảnh với kịch bản: Kiểm tra phôi cục bộ -> Tìm stock Pexels/Pixabay trực tuyến -> Gọi Stable Diffusion / DALL-E sinh ảnh nếu thiếu).
- **Đầu ra:** Thư mục `projects/{project_slug}/assets/` và file ánh xạ `scene_mapping.json`.

### Module 4: Video Composer (`editor/video_editor.py`) [MODIFY]
- **Chức năng:** Bổ sung hàm `build_content_video()` dựng video theo cấu trúc phân cảnh ngữ nghĩa thay vì cắt clip ngẫu nhiên.
- **Kỹ thuật dựng:**
  - Lồng tiếng tự động qua Edge-TTS (`vi-VN-HoaiAnNeural` hoặc `vi-VN-NamMinhNeural`).
  - Ghép ảnh/video khớp thời lượng voiceover từng phân cảnh.
  - Áp dụng hiệu ứng Ken Burns (pan/zoom chuyển động camera nhẹ cho ảnh tĩnh).
  - Burn phụ đề tự động từng phân cảnh, ghép nhạc nền từ `bgm_manager.py`.

### Module 5: Publisher (`tools/publisher.py` & `tools/auto_uploader.py`) [NEW]
- **Chức năng:** Gửi video và nội dung caption kèm hashtag qua Telegram Bot hiện có; cung cấp script Selenium độc lập hỗ trợ auto-upload.

### GUI Integration (`gui/tabs/content_recycler_tab.py`) [NEW]
- **Chức năng:** Tab CustomTkinter trực quan hóa luồng công việc 5 bước. Cho phép:
  - Nhập URL gốc và chạy cào nguồn.
  - Xem và sửa trực tiếp kịch bản kịch bản phân cảnh JSON trước khi render.
  - Xem danh mục ảnh phôi đã cào và tùy chọn thay thế.
  - Chạy dựng video và gửi báo cáo tiến trình thời gian thực.

---

## 3. Định dạng Dữ liệu Trung gian (Data Formats)

### Định dạng `script.json` (Kịch bản phân cảnh)
```json
{
    "title": "Tiết kiệm 70 lần Token cho Claude Code",
    "platform": "tiktok",
    "caption": "Bí quyết giúp tiết kiệm ví tiền cho nhà phát triển khi dùng Claude Code...",
    "hashtags": ["#claudecode", "#aitools", "#developer"],
    "scenes": [
        {
            "scene_id": 1,
            "narration": "Bạn có biết Claude Code đang đốt token của bạn lãng phí gấp bảy mươi lần không?",
            "visual_keywords": ["claude code", "expensive tokens", "programmer facepalm"],
            "visual_type": "concept_image",
            "duration_hint": 5.2
        },
        {
            "scene_id": 2,
            "narration": "Đừng lo, giải pháp ở đây là xây dựng sơ đồ tri thức cho dự án của bạn.",
            "visual_keywords": ["knowledge graph", "code relationship map", "refify tool"],
            "visual_type": "tech_screenshot",
            "duration_hint": 4.8
        }
    ]
}
```

---

## 4. Kế hoạch Kiểm thử & Xác minh (Verification Plan)

### Kiểm thử Tự động:
- Viết script test độc lập chạy CLI kiểm thử luồng từ cào video gốc đến xuất ra kịch bản phân cảnh và sinh âm thanh Edge-TTS hoàn tất.
- Kiểm thử tích hợp khả năng cào hình ảnh của `asset_crawler.py` theo chủ đề cụ thể và đảm bảo tải ảnh về thư mục phôi chính xác.

### Xác minh Thủ công:
- Chạy giao diện GUI mới thông qua `main_gui.py`, thực hiện toàn bộ luồng tạo dự án, sửa kịch bản trực tiếp trên màn hình GUI, bấm render video và kiểm tra chất lượng video đầu ra trong thư mục `exports/`.
