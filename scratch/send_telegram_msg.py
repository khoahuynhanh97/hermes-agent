import urllib.request
import urllib.parse
import json

token = "7756335704:AAHrpj1RyFLZHQ1xim4P_erWwWeZvAth5ik"
chat_id = 5069349064
message = (
    "Kết nối hoạt động tốt — giờ luồng hoàn chỉnh là:\n\n"
    "Bạn upload file bot_telegram lên đây → mình review code\n"
    "Mình ra prompt/spec → đẩy thẳng sang Telegram cho bạn\n"
    "Bot nhận, Codex triển khai → report .md bạn upload lên đây → mình review tiếp\n"
    "Upload file bot_telegram lên là bắt đầu vòng lặp đầu tiên ngay thôi!"
)

url = f"https://api.telegram.org/bot{token}/sendMessage"
data = {
    "chat_id": chat_id,
    "text": message
}

req_data = json.dumps(data).encode("utf-8")
req = urllib.request.Request(
    url, 
    data=req_data, 
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req) as response:
        res_data = response.read().decode("utf-8")
        print("Response:", res_data)
except Exception as e:
    print("Error sending message:", e)
