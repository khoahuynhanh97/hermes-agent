# Reviewer App Wakeup Result

- Source chat id: 5069349064
- Message id: 9695
- Category: worker_job
- Source kind: document
- Source file: proposed_upgrades.md
- Downloaded path: C:\Work\Code\Upgrade_chat_bot\Reviewer_app\reports\telegram_inbox\20260702_133641_msg_9695_proposed_upgrades.md
- Wakeup prompt created at: 2026-07-02 13:36:44

# Codex Review Wakeup

Day la prompt danh thuc Codex reviewer. Reviewer_app chi chuyen report va yeu cau, khong tu review va khong tu sua code.

## Context

- Source chat id: 5069349064
- Message id: 9695
- Category: worker_job
- Source kind: document
- Source file: proposed_upgrades.md
- Downloaded path: C:\Work\Code\Upgrade_chat_bot\Reviewer_app\reports\telegram_inbox\20260702_133641_msg_9695_proposed_upgrades.md
- Created at: 2026-07-02 13:36:44

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

Đề xuất nâng cấp & Tối ưu hóa hệ thống Hermes (Đề xuất #002, #003, #004).

# ĐỀ XUẤT NÂNG CẤP & TỐI ƯU HÓA HỆ THỐNG (PROPOSED UPGRADES)

- **Tác giả:** Antigravity (Local IDE Agent)
- **Trạng thái:** Chờ phê duyệt (Pending Approval)
- **Tệp tin phân tích tham chiếu:** `reports/hermes_system_analysis.md`

---

## 🛠️ Đề xuất #002: Tái cấu trúc tách nhỏ `gui/app.py`

### 1. Phân tích hiện trạng
Tệp [gui/app.py](file:///c:/Work/Code/Hermes_download/hermes-agent/gui/app.py) dài gần 3500 dòng code. Nó đang gộp chung:
- Khai báo giao diện chính (`HermesTikTokVideoFactoryApp`).
- Các hàm quản lý Threading chạy tải/xử lý tài nguyên.
- Logic vẽ và tương tác của từng Tab: "Tải tài nguyên", "Biên dịch Kịch bản", "Dịch từ khóa", "Quản lý Dự án".

Điều này làm ứng dụng dễ lỗi giao diện khi nâng cấp và khó viết Unit Test cho logic nghiệp vụ.

### 2. Thiết kế đề xuất
Chúng ta sẽ tách giao diện chính thành các lớp Tab độc lập:
- `gui/download_tab.py`: Quản lý giao diện & thread tải từ Pexels, Pixabay, Supplier Feed.
- `gui/script_tab.py`: Quản lý giao diện viết kịch bản và gọi API OpenAI/Gemini để sinh kịch bản.
- `gui/keywords_tab.py`: Quản lý giao diện dịch thuật và đề xuất từ khóa.
- `gui/app.py` chỉ giữ lại cấu trúc khung (Sidebar, Header) và nạp các lớp Tab này vào giao diện.

---

## 🛡️ Đề xuất #003: Chuẩn hóa bảo mật nạp cấu hình (.env)

### 1. Phân tích hiện trạng
Trong [config.py](file:///c:/Work/Code/Hermes_download/hermes-agent/config.py), các khóa nhạy cảm:
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`

vẫn có các giá trị mặc định dạng `"YOUR_..._HERE"` ghi trực tiếp. Điều này gây nguy hiểm nếu vô tình bị commit lên GitHub.

### 2. Thiết kế đề xuất
1. Sửa đổi `config.py` để sử dụng duy nhất cơ chế đọc từ biến môi trường qua `os.environ` hoặc nạp từ `.env`.
2. Tạo tệp `.env.example` mẫu để người dùng mới cấu hình mà không cần mở sửa mã nguồn python.
3. Thêm hàm kiểm tra `verify_config()` lúc khởi động Bot Telegram và GUI Desktop, nếu thiếu cấu hình thì đưa ra cảnh báo đẹp mắt thay vì để chương trình crash ngầm.

---

## 🗑️ Đề xuất #004: Tự động dọn dẹp Video tạm trong `JobWatcher`

### 1. Phân tích hiện trạng
Hàm `_resolve_media_for_analysis` trong [core/job_watcher.py](file:///c:/Work/Code/Hermes_download/hermes-agent/core/job_watcher.py) tải video phôi về thư mục cục bộ `projects/[project_slug]/agent_outputs/[job_id]/source_video/`.
Sau khi phân tích bằng Gemini và sinh ra file `analysis.md` thành công, video phôi vẫn tồn tại mãi mãi trong ổ cứng. Với các video dài hoặc chạy nhiều Job, ổ cứng của máy tính sẽ nhanh chóng bị đầy.

### 2. Thiết kế đề xuất
Thêm một bước dọn dẹp (Cleanup Phase) vào cuối hàm `execute_job_tasks` hoặc khối xử lý phân tích trong `core/job_watcher.py`:
```python
# Sau khi hoàn tất ghi phân tích
if media_path and media_path.exists() and "source_video" in str(media_path):
    try:
        media_path.unlink()
        logger.info(f"  -> Đã dọn dẹp video tạm tiết kiệm bộ nhớ: {media_path.name}")
    except Exception as e:
        logger.warning(f"  -> Không thể dọn dẹp file tạm: {e}")
```

