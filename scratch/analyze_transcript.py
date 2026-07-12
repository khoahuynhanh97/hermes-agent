import os
import sys
import google.generativeai as genai
from dotenv import load_dotenv

# Thêm thư mục gốc vào path để import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

# Force stdout to UTF-8
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    load_dotenv()
    
    api_key = config.GEMINI_API_KEY
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        api_key = os.environ.get("GEMINI_API_KEY", "")
        
    if not api_key:
        print("❌ Lỗi: Chưa cấu hình GEMINI_API_KEY trong .env")
        sys.exit(1)
        
    genai.configure(api_key=api_key)
    
    transcript_path = 'scratch/clean_transcript.txt'
    if not os.path.exists(transcript_path):
        print(f"❌ Lỗi: Không tìm thấy file transcript tại {transcript_path}")
        sys.exit(1)
        
    with open(transcript_path, 'r', encoding='utf-8') as f:
        transcript_content = f.read()
        
    print("[*] Đang gửi transcript lên Gemini để phân tích chuyên sâu...")
    
    prompt = f"""
Bạn là một chuyên gia tự động hóa (Automation Expert) và kĩ sư AI.
Dưới đây là bản transcript ghi âm từ một video YouTube hướng dẫn về cách sử dụng Claude Code để tự động hóa xây dựng workflow trên n8n thông qua giao thức MCP (Model Context Protocol).

Hãy phân tích kỹ nội dung transcript và viết một hướng dẫn chi tiết, có cấu trúc rõ ràng bằng tiếng Việt. Báo cáo cần bao gồm:

1. **TỔNG QUAN HỆ THỐNG & WORKFLOW**:
   - Giải thích ý tưởng cốt lõi của video: Claude Code + n8n + MCP là gì? Tại sao sự kết hợp này lại mạnh mẽ?
   
2. **HƯỚNG DẪN CẤU HÌNH CHI TIẾT (Step-by-step Setup)**:
   - Cài đặt và cấu hình Claude Code CLI.
   - Cài đặt và cấu hình n8n MCP Server. Các tham số cấu hình cần thiết (API Key, URL, Access Token, v.v...).
   - Cách tích hợp NVIDIA Developer API (để dùng mô hình miễn phí/tối ưu chi phí) hoặc Nine Router.
   
3. **CÁC LỆNH TƯƠNG TÁC THỰC TẾ (Claude Code Commands)**:
   - Các lệnh tiếng Việt/tiếng Anh mà người dùng gõ vào Claude Code để yêu cầu tạo, đọc, giải thích hoặc chỉnh sửa workflow trong n8n (ví dụ: tạo node Telegram, kiểm tra lỗi, push lên n8n).

4. **QUY TRÌNH WORKFLOW MẪU (Workflow Demo)**:
   - Tóm tắt kịch bản demo trong video (ví dụ: kết nối Telegram, cào dữ liệu, xử lý AI, v.v...).
   
5. **CÁC TIỆN ÍCH KHÁC ĐƯỢC GIỚI THIỆU**:
   - Giới thiệu ngắn gọn về công cụ NCA Toolkit (được dùng để render video tự động tại local).

6. **BÀI HỌC CỐT LÕI & LƯU Ý KHI TRIỂN KHAI**:
   - Các lưu ý quan trọng về bảo mật, quản lý API key, tối ưu chi phí và kiểm soát lỗi khi để AI tự động sửa workflow.

Vui lòng viết báo cáo cực kỳ chất lượng, chi tiết, chuyên nghiệp dưới định dạng Markdown, sử dụng code blocks cho các lệnh CLI hoặc cấu hình JSON.

Dưới đây là transcript:
---
{transcript_content}
---
"""

    model_name = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    model = genai.GenerativeModel(model_name=model_name)
    
    try:
        response = model.generate_content(prompt)
        report_content = response.text
        
        # Save output report
        output_dir = 'knowledge_base'
        os.makedirs(output_dir, exist_ok=True)
        report_path = os.path.join(output_dir, 'claude-code-n8n-workflow-mcp.md')
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
            
        print(f"\n✅ Phân tích thành công! Báo cáo chi tiết đã được lưu tại: {os.path.abspath(report_path)}")
        
    except Exception as e:
        print(f"❌ Gặp lỗi khi gọi Gemini API: {e}")

if __name__ == "__main__":
    main()
