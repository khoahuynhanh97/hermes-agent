import os
import sys
import ollama

# Thêm thư mục gốc vào path để from hermes.runtime import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.runtime import config

def get_ollama_client():
    """Tạo client kết nối đến Ollama dựa trên config"""
    host = getattr(config, "OLLAMA_API_URL", "http://localhost:11434")
    return ollama.Client(host=host)

def check_ollama():
    """
    Kiểm tra xem Ollama có đang chạy không và mô hình cấu hình đã được tải chưa.
    
    Returns:
        (bool, bool, list): (is_running, model_installed, list_of_models)
    """
    model_name = getattr(config, "DEFAULT_LOCAL_MODEL", "llama3.2:3b")
    client = get_ollama_client()
    try:
        model_list = client.list()
        models = model_list.get("models", [])
        installed_names = [m.get("name", "") for m in models]
        
        # Kiểm tra sự tồn tại của model (chấp nhận cả phiên bản không tag hoặc tag khác)
        model_installed = False
        for name in installed_names:
            if name.startswith(model_name) or model_name in name:
                model_installed = True
                break
                
        return True, model_installed, installed_names
    except Exception as e:
        print(f"[!] Không thể kết nối tới Ollama tại {client._client.base_url}: {e}")
        return False, False, []

def generate_tiktok_script(topic, style="hài hước, chia sẻ kiến thức", duration="60s", reference_analysis=None):
    """
    Sử dụng Ollama Local Model để sinh kịch bản TikTok tối ưu giữ chân người xem.
    
    Args:
        topic (str): Chủ đề chính của video.
        style (str): Phong cách diễn đạt (ví dụ: giật gân, tâm sự, hài hước, công nghệ...).
        duration (str): Thời lượng ước tính (ví dụ: 30s, 60s, 3 phút...).
        reference_analysis (str, optional): Nội dung phân tích từ video mẫu để học hỏi.
        
    Returns:
        str: Kịch bản TikTok hoàn chỉnh do AI viết.
    """
    is_running, model_installed, installed = check_ollama()
    model_name = getattr(config, "DEFAULT_LOCAL_MODEL", "llama3.2:3b")
    
    if not is_running:
        return (
            "Lỗi: Không thể kết nối tới Ollama.\n"
            "Hướng dẫn khắc phục:\n"
            "1. Vui lòng mở ứng dụng Ollama trên máy tính của bạn.\n"
            "2. Đảm bảo cổng kết nối trong config.py trùng khớp với cổng của Ollama.\n"
        )
        
    if not model_installed:
        return (
            f"Lỗi: Mô hình '{model_name}' chưa được cài đặt trong Ollama của bạn.\n"
            f"Các mô hình hiện có: {installed}\n"
            "Hướng dẫn khắc phục:\n"
            f"Mở terminal và chạy lệnh sau để tải mô hình:\n"
            f"   ollama pull {model_name}\n"
        )

    client = get_ollama_client()
    
    system_prompt = """Bạn là một biên kịch TikTok chuyên nghiệp, hiểu rất rõ thuật toán giữ chân người xem của TikTok.
Nhiệm vụ của bạn là viết một kịch bản TikTok hấp dẫn, ngắn gọn, súc tích bằng tiếng Việt.

Kịch bản cần có cấu trúc chuẩn như sau:
1. **TIÊU ĐỀ VIDEO** (Gợi sự tò mò)
2. **PHẦN HOOK (3-5 giây đầu)**: Đánh trúng nỗi đau, câu hỏi gây tò mò cực độ hoặc hình ảnh gây shock để người xem không lướt qua.
3. **PHẦN NỘI DUNG CHÍNH (Body)**: Đi thẳng vào vấn đề, không dài dòng. Chia làm 2-3 ý rõ ràng. Sử dụng câu ngắn, từ ngữ đời thường, hình ảnh liên tưởng mạnh.
4. **PHẦN KÊU GỌI HÀNH ĐỘNG (CTA - 3 giây cuối)**: Kêu gọi bình luận ý kiến, follow để xem phần tiếp theo hoặc bấm vào link sinh học.
5. **GỢI Ý HÌNH ẢNH / HIỆU ỨNG (B-roll & Sound effects)**: Thêm chỉ dẫn cho người dựng video trong dấu ngoặc vuông [Ví dụ: Cảnh zoom cận cảnh, tiếng ting ting...].

Hãy trả về kịch bản chất lượng cao nhất, không cần viết lời dẫn giải hay chào hỏi bên ngoài."""

    user_content = f"Viết kịch bản TikTok về chủ đề: '{topic}'.\nPhong cách: {style}.\nThời lượng ước tính: {duration}.\n"
    
    if reference_analysis:
        user_content += f"\nDưới đây là thông tin phân tích từ một video mẫu mà bạn nên học hỏi cấu trúc hoặc phong cách:\n{reference_analysis}\n"
        
    print(f"[*] Đang yêu cầu Ollama sinh kịch bản bằng model: {model_name}...")
    try:
        response = client.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            options={
                "temperature": 0.7,
                "top_p": 0.9
            }
        )
        return response["message"]["content"]
    except Exception as e:
        return f"Lỗi trong quá trình sinh kịch bản qua Ollama: {e}"

if __name__ == "__main__":
    # Test thử trực tiếp
    is_ok, has_model, _ = check_ollama()
    if is_ok:
        topic_test = input("Nhập chủ đề video bạn muốn viết kịch bản: ")
        if topic_test.strip():
            result = generate_tiktok_script(topic_test.strip())
            print("\n=== KỊCH BẢN TIKTOK ===")
            print(result)
    else:
        print("[!] Không kết nối được Ollama để test.")
