---
name: memo
description: Quản lý ghi chú nhanh (Personal Memos / Quick Notes) có phân loại nhóm (group) và gắn thẻ (#tags). Không dùng cho Knowledge Base.
allowed-tools:
  - memo_create
  - memo_search
  - memo_list
  - memo_update
  - memo_delete
  - memo_tags_list
  - memo_groups_list
---

# Hướng dẫn Quản lý Ghi chú Cá nhân (Personal Memos)

Kỹ năng này phục vụ cho việc **ghi chú cá nhân, ý tưởng, việc cần làm, nhắc nhở (Scratchpad/Notes)**.
> **LƯU Ý QUAN TRỌNG**: Memo/Ghi chú hoàn toàn **khác** với Knowledge Base (/hoc). Memo không cần duyệt (HITL) hay dẫn nguồn chứng cứ, mà là không gian lưu trữ nhanh của chính người dùng.

## Khi nào kích hoạt kỹ năng này?
- Người dùng yêu cầu ghi chú: "Ghi chú...", "Lưu memo...", "Note lại...", "Nhớ giúp tôi..."
- Người dùng tìm kiếm ghi chú: "Tìm ghi chú...", "Xem các memo tag #...", "Liệt kê ghi chú nhóm..."
- Người dùng sửa/xóa ghi chú cá nhân.

## Hướng dẫn thực hiện

### 1. Tạo Ghi chú (`memo_create`)
- **Phân tích nội dung**:
  - Trích xuất `#tag` nếu người dùng có nhập (ví dụ: `#idea`, `#todo`, `#ai`).
  - Xác định nhóm `group_name` phù hợp: `ideas`, `work`, `personal`, `todo`, `shopping`, hoặc `general`.
  - Đặt tiêu đề `title` ngắn gọn, súc tích (nếu người dùng không cung cấp tiêu đề riêng).
- Gọi `memo_create(title=..., content=..., group_name=..., tags=[...], pinned=...)`.
- Phản hồi ngắn gọn xác nhận kèm ID và tags.

### 2. Tìm kiếm Ghi chú (`memo_search`)
- Dùng `memo_search(query=..., group_name=..., tag=...)` để tìm kiếm toàn văn nhanh (FTS5).
- Hiển thị kết quả rõ ràng: Tiêu đề, nội dung tóm tắt, nhóm, tags, và ID.

### 3. Liệt kê & Phân loại (`memo_list`, `memo_tags_list`, `memo_groups_list`)
- Khi người dùng muốn xem danh mục tags hoặc các nhóm:
  - Gọi `memo_tags_list()` hoặc `memo_groups_list()`.
  - Hiển thị dạng thẻ: `#idea (5)`, `#work (3)`.

### 4. Cập nhật & Xóa (`memo_update`, `memo_delete`)
- Dùng `memo_id` để cập nhật trạng thái (ghim/bỏ ghim, lưu trữ, sửa nội dung) hoặc xóa vĩnh viễn.
