# Local Prompt Library

Folder này dùng để lưu các prompt mẫu mà bạn muốn tái sử dụng.

## Cách dùng nhanh

- Lưu mỗi prompt thành một file `.md` trong `prompt_library/templates/`.
- Đặt `id:` trong phần metadata để gọi lại, ví dụ `promptA` hoặc `promptB`.
- Dùng biến dạng `{{ product_name }}`, `{{ selling_points }}`, `{{ background_note }}` để thay dữ liệu khi render.

Ví dụ:

```powershell
python scripts/render_prompt.py promptA --var product_name="Giá đỡ điện thoại gập gọn" --var selling_points="gập gọn, chỉnh góc, chống trượt"
```

Khi chat với Codex, bạn có thể nói:

```text
Dùng promptA để viết voice bán hàng cho sản phẩm này...
Dùng promptB để tạo ảnh theo background này...
```

Codex sẽ đọc file prompt tương ứng trong folder này và dùng lại đúng cấu trúc đã lưu.

## Format file prompt

```markdown
---
id: promptA
name: Voice bán hàng TikTok
type: voice_script
description: Prompt mẫu viết kịch bản voice quảng cáo.
---

Nội dung prompt ở đây...
Tên sản phẩm: {{ product_name }}
Điểm bán hàng: {{ selling_points }}
```

## Gợi ý phân loại

- `voice_script`: prompt viết voice/kịch bản bán hàng.
- `image_prompt`: prompt tạo ảnh quảng cáo.
- `video_prompt`: prompt tạo video AI.
- `analysis`: prompt phân tích sản phẩm, đối thủ, insight.
