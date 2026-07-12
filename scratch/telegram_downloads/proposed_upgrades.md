# ĐỀ XUẤT NÂNG CẤP & TỐI ƯU HÓA HỆ THỐNG (PROPOSED UPGRADES)

- **Tác giả:** Antigravity Watcher
- **Trạng thái:** Chờ phê duyệt (Pending Approval)

---

## 🛠️ Đề xuất #002: Tái cấu trúc tách nhỏ `gui/app.py`
- Tách các tab chức năng ra thành lớp độc lập trong `gui/`.

## 🛡️ Đề xuất #003: Chuẩn hóa bảo mật cấu hình (.env)
- Nạp API keys trực tiếp qua dotenv.

## 🗑️ Đề xuất #004: Tự động xóa video tạm trong `JobWatcher`
- Thêm bước xóa file mp4 phôi trong source_video/ sau khi hoàn thành task.
