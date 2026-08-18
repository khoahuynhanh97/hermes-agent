# Hướng dẫn sử dụng Giao diện Desktop Hermes Video Downloader 🖥️

Ứng dụng Desktop **Hermes Video Downloader** cung cấp một giao diện cửa sổ hiện đại (Dark Mode), trực quan và dễ sử dụng để cào và tải video hàng loạt từ nhiều nền tảng Trung Quốc (Douyin, Kuaishou, Xiaohongshu, Weibo, Bilibili, 1688, Taobao...) và quốc tế (TikTok, YouTube Shorts, Instagram, Facebook Reels, Pinterest, Lemon8...) về máy tính làm nguyên liệu dựng video.

---

## 🚀 Cách khởi chạy ứng dụng

1.  Mở PowerShell hoặc Command Prompt trên máy tính của bạn.
2.  Chuyển hướng đến thư mục dự án:
    ```powershell
    cd D:\work\hermes-agent
    ```
3.  Chạy lệnh khởi động giao diện Desktop:
    ```powershell
    python main_gui.py
    ```

*Mẹo: Bạn có thể tạo một file shortcut (.bat) ngoài Desktop chứa lệnh trên để mở nhanh phần mềm chỉ bằng một cú nhấp đúp.*

---

## 🛠 Hướng dẫn các tính năng trên giao diện

Giao diện được chia thành 2 cột rất dễ thao tác:

### 1. Bảng điều khiển (Cột bên trái)
*   **Vượt rào bảo mật (Cookie)**: Chọn tên trình duyệt bạn đang sử dụng (ví dụ: `Chrome`, `Edge`, `Brave`...) đã đăng nhập sẵn các tài khoản mạng xã hội của bạn. Ứng dụng sẽ tự động trích xuất cookie để vượt captcha hoặc các trang bắt đăng nhập (như Instagram, Facebook, Xiaohongshu).
*   **Giới hạn thời lượng**: Thanh lọc thời lượng. Ví dụ bạn chọn **Dưới 120 giây (2 phút)**, ứng dụng sẽ tự động bỏ qua tất cả các video dài quá 2 phút trước khi tải về để tiết kiệm dung lượng mạng.
*   **Định dạng đầu ra**: Chọn tải **Video (MP4)** hoặc chỉ tách **Audio (MP3)** lấy nhạc nền.
*   **Thư mục lưu trữ**: Hiển thị đường dẫn lưu video hiện tại. Bạn có thể bấm nút **Đổi thư mục lưu** để thay đổi thư mục lưu trữ.
*   **Nút "Mở thư mục lưu"**: Bấm vào đây để mở nhanh thư mục lưu trữ video trên Windows Explorer và lấy nguyên liệu.

### 2. Vùng làm việc chính (Cột bên phải)
*   **Hộp dán Link**: Bạn dán danh sách các link video (TikTok, YouTube, Douyin, 1688...) tại đây. Hỗ trợ **nhập hàng loạt (mỗi dòng một link)**.
*   **Nút "BẮT ĐẦU CÀO & TẢI VIDEO"**: Nhấp vào nút này để bắt đầu tiến trình tải.
*   **Bảng Tiến Trình (Log Console)**: Hiển thị nhật ký tải xuống và thanh phần trăm tiến độ của từng tệp trong thời gian thực. Tiến trình được thiết lập chạy ngầm nên **cửa sổ ứng dụng sẽ không bao giờ bị đơ hay đóng băng** trong lúc tải.

---

## 💡 Hướng dẫn tải từ các trang TMĐT Trung Quốc (1688, Taobao, JD...)
*   **Cách lấy link**: Bạn copy đường dẫn sản phẩm trên trình duyệt (ví dụ: link chi tiết sản phẩm trên `1688.com`, `taobao.com` hoặc `jd.com`).
*   **Tải video**: Dán link sản phẩm vào hộp dán link của ứng dụng. Ứng dụng sẽ tự động phân tích mã nguồn HTML để quét lấy liên kết video giới thiệu sản phẩm MP4 gốc chất lượng cao và tải trực tiếp về máy cho bạn.
