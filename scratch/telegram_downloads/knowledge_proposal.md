# Knowledge Proposal

Source: https://vt.tiktok.com/ZSCmvCjd8/
Ghi chu: Telegram request: /hoc_kien_thuc. Learn the knowledge shared in the video. Extract tools, concepts, workflow steps, key facts, cautions, and how Hermes can use this knowledge. Do not default to sales hooks, CTA, storyboard, or prompt packs unless the video itself teaches those. Do not overwrite the shared knowledge base automatically; write knowledge_proposal.md for human review.
Trang thai: needs_source_media

## Ket luan

Chua the rut tri thuc that vi worker chua doc duoc video/transcript. Khong tao knowledge production tu URL tran.

## Can bo sung

- Gui truc tiep file video cho bot bang caption `/hoc_kien_thuc`.
- Hoac dan transcript/mo ta video vao note.
- Hoac ghi ro cac cong cu/buoc lam ma video de cap.

## Analysis log

Dưới đây là báo cáo kiến thức từ video:

1.  **Chủ đề thật của video:**
    Cập nhật phiên bản 9Router v0.5.12: Tổng quan về các tính năng, cải tiến, sửa lỗi và hướng dẫn cập nhật khuyến nghị cho người dùng 9Router.

2.  **Các công cụ, nền tảng, dịch vụ hoặc khái niệm được nhắc đến:**
    *   **9Router:** Phần mềm router AI.
    *   **CLI Tools:** Công cụ dòng lệnh.
    *   **AI Router & Token Saver:** Khái niệm cốt lõi của 9Router.
    *   **Token dashboard:** Bảng điều khiển quản lý token.
    *   **Provider catalog:** Danh mục các nhà cung cấp dịch vụ AI.
    *   **Streaming:** Tính năng phản hồi theo luồng.
    *   **Claude Code, Codex, Cursor, OpenClaw, Cline, Copilot, Antigravity, Venice AI, Blackbox, DeepSeek, Gemini, CodeBuddy:** Các nhà cung cấp hoặc công cụ AI cụ thể được 9Router hỗ trợ.
    *   **OpenAI-compatible endpoint:** Giao diện tương thích với API của OpenAI.
    *   **Token saver:** Tính năng tiết kiệm token.
    *   **Quota tracking:** Theo dõi hạn mức sử dụng.
    *   **Auto fallback:** Tự động chuyển đổi dự phòng.
    *   **Usage logs:** Nhật ký sử dụng.
    *   **Streaming usage:** Sử dụng tính năng streaming.
    *   **Token flow:** Luồng xử lý token.
    *   **Kiro SSO (external_idp Microsoft + IDC org token):** Tính năng Single Sign-On của Kiro liên quan đến Microsoft và token tổ chức IDC.
    *   **Responses text format và reasoning effort:** Định dạng phản hồi văn bản và nỗ lực suy luận (liên quan đến Codex).
    *   **Native generateContent endpoint:** Điểm cuối tạo nội dung gốc (liên quan đến Gemini TTS).
    *   **Non-JSON SSE:** Các dòng Server-Sent Events không phải định dạng JSON.
    *   **Duplicate DONE:** Xử lý các thông báo "DONE" trùng lặp.
    *   **Antigravity retry:** Tính năng thử lại cho các lỗi upstream tạm thời.
    *   **Auth redirect:** Chuyển hướng xác thực.
    *   **Bulk delete:** Xóa hàng loạt.
    *   **Docker compose (.yml) Headroom:** Cấu hình Docker Compose liên quan đến quản lý tài nguyên (Headroom).
    *   **Card layout (token-saver):** Bố cục hiển thị thông tin token-saver.
    *   **Diagnostics (token vs billing):** Chẩn đoán để phân biệt số liệu token với hóa đơn thực tế.
    *   **Config (provider, token, combo):** Cấu hình của 9Router.
    *   **Combo/route:** Các thiết lập định tuyến kết hợp nhiều provider.
    *   **Rate limit:** Giới hạn tốc độ yêu cầu.

3.  **Vai trò của từng công cụ/khái niệm:**
    *   **9Router:** Là trung tâm của hệ thống, một lớp router AI giúp quản lý và định tuyến các yêu cầu tới nhiều nhà cung cấp AI khác nhau thông qua một endpoint tương thích OpenAI, đồng thời cung cấp các tính năng tiết kiệm token, theo dõi hạn mức và tự động chuyển đổi dự phòng.
    *   **CLI Tools:** Các công cụ để tương tác với 9Router từ dòng lệnh.
    *   **AI Router & Token Saver:** Mô tả chức năng chính của 9Router là định tuyến AI và giúp người dùng tiết kiệm token.
    *   **Token dashboard:** Cung cấp giao diện để người dùng theo dõi và quản lý việc sử dụng token.
    *   **Provider catalog:** Danh sách các dịch vụ AI có sẵn để 9Router có thể định tuyến đến.
    *   **Streaming:** Cơ chế mà 9Router cung cấp để nhận các phản hồi theo thời gian thực từ các mô hình AI.
    *   **Các nhà cung cấp AI (Claude Code, Codex, v.v.):** Là các dịch vụ AI thực tế mà 9Router kết nối và định tuyến yêu cầu tới.
    *   **OpenAI-compatible endpoint:** Đảm bảo khả năng tương thích với các ứng dụng được xây dựng cho OpenAI API.
    *   **Token saver, Quota tracking, Auto fallback:** Các tính năng giúp tối ưu hóa chi phí, quản lý tài nguyên và tăng độ tin cậy của việc sử dụng AI.
    *   **Usage logs, Streaming usage, Token flow:** Các thông tin trên dashboard giúp người dùng hiểu rõ hơn về cách token được sử dụng và các vấn đề liên quan đến streaming.
    *   **Kiro SSO, Responses text format, generateContent endpoint:** Là các khía cạnh cụ thể của các nhà cung cấp Kiro, Codex, Gemini đã được sửa lỗi hoặc cải thiện trong bản cập nhật.
    *   **Non-JSON SSE, Duplicate DONE, Antigravity retry, Auth redirect:** Các cải tiến trong xử lý streaming và ổn định xác thực.
    *   **Bulk delete, Docker compose Headroom, Card layout, Diagnostics:** Các tính năng quản lý và vận hành giúp 9Router dễ sử dụng và theo dõi hơn.
    *   **Config, Combo/route:** Các cài đặt mà người dùng cần sao lưu và kiểm tra sau khi cập nhật.
    *   **Rate limit:** Hạn chế mà 9Router giúp người dùng vượt qua bằng cách định tuyến thông minh.

4.  **Quy trình từng bước mà video hướng dẫn (Quy trình cập nhật 9Router v0.5.12):**
    1.  **Backup config:** Sao lưu cấu hình hiện có (provider, token, combo).
    2.  **Update v0.5.12:** Cập nhật 9Router lên phiên bản 0.5.12 (khuyến nghị nếu dùng hàng ngày).
    3.  **Test provider chính:** Kiểm tra các nhà cung cấp AI chính như Kiro, Copilot, Codex, Gemini.
    4.  **Test fallback:** Kiểm tra các cơ chế chuyển đổi dự phòng quan trọng (combo/route).

5.  **Đầu vào và đầu ra của từng bước:**
    *   **Bước 1: Backup config**
        *   **Đầu vào:** Cấu hình 9Router hiện tại (provider connections, token keys, combo routing rules).
        *   **Đầu ra:** Bản sao lưu file cấu hình hoặc thông tin cấu hình quan trọng.
    *   **Bước 2: Update v0.5.12**
        *   **Đầu vào:** Phiên bản 9Router cũ (đặc biệt v0.5.8 trở xuống).
        *   **Đầu ra:** Phiên bản 9Router v0.5.12 đã được cài đặt.
    *   **Bước 3: Test provider chính**
        *   **Đầu vào:** Yêu cầu mẫu (prompts) để kiểm tra các nhà cung cấp AI đã cấu hình (Kiro, Copilot, Codex, Gemini).
        *   **Đầu ra:** Xác nhận các nhà cung cấp chính hoạt động chính xác và ổn định.
    *   **Bước 4: Test fallback**
        *   **Đầu vào:** Yêu cầu mẫu được thiết kế để kích hoạt cơ chế fallback hoặc sử dụng các combo/route quan trọng.
        *   **Đầu ra:** Xác nhận cơ chế fallback hoạt động đúng như mong đợi khi một provider gặp sự cố hoặc quá tải.

6.  **Lưu ý, giới hạn, điều kiện áp dụng, phần nào chưa rõ:**
    *   **Khuyến nghị cập nhật:** Khuyên người dùng đang sử dụng 9Router hàng ngày, đặc biệt là các phiên bản cũ hơn v0.5.8, để route model, tiết kiệm token hoặc chống rate limit thì nên cập nhật.
    *   **Điều kiện tiên quyết:** Cần sao lưu cấu hình trước khi tiến hành cập nhật.
    *   **Kiểm tra sau cập nhật:** Bắt buộc kiểm tra lại các provider chính (Kiro, Copilot, Codex, Gemini) và cơ chế fallback (combo/route quan trọng) trước khi sử dụng trong các workflow production.
    *   **Phần chưa rõ:** Video không cung cấp chi tiết về cách thực hiện các lệnh cập nhật hoặc cách sao lưu/kiểm tra cụ thể. Các khái niệm như "Headroom" trong Docker compose hay "DeepSeek thinking compatible" được nêu ra nhưng không giải thích sâu về ý nghĩa kỹ thuật hoặc lợi ích cụ thể.

7.  **Hermes có thể dùng kiến thức này vào module/lệnh/workflow nào:**
    *   **Module "AI Router Management":** Hermes có thể quản lý các phiên bản 9Router của người dùng, đưa ra thông báo về các bản cập nhật quan trọng.
    *   **Lệnh `/9router_update_guide`:** Cung cấp hướng dẫn chi tiết từng bước để cập nhật 9Router, bao gồm các bước sao lưu và kiểm tra cần thiết.
    *   **Workflow "AI Cost Optimization":** Sử dụng kiến thức về Token Saver Dashboard, Token Flow, Diagnostics (token vs billing) để giúp người dùng hiểu rõ hơn về chi phí AI và cách tối ưu hóa thông qua 9Router.
    *   **Lệnh `/9router_features_v0_5_12`:** Liệt kê các tính năng mới và cải tiến trong bản v0.5.12, giúp người dùng nắm bắt nhanh các thay đổi.
    *   **Lệnh `/9router_supported_providers`:** Cung cấp danh sách các nhà cung cấp AI được 9Router hỗ trợ và các cập nhật liên quan đến họ.
    *   **Chức năng cảnh báo/khuyến nghị:** Hermes có thể tự động cảnh báo người dùng 9Router đang chạy phiên bản cũ về bản cập nhật và các rủi ro tiềm ẩn (nếu không cập nhật).
    *   **Troubleshooting Assistant:** Tích hợp các fix lỗi thực dụng (Kiro SSO, Codex response format, Gemini TTS, Streaming ổn định) vào một công cụ hỗ trợ xử lý sự cố cho người dùng 9Router.
    *   **Cấu hình Docker Compose:** Hermes có thể cung cấp các mẫu docker-compose.yml đã được tối ưu (ví dụ: bật Headroom mặc định) cho người dùng 9Router.
