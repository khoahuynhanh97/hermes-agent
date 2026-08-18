import sys
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient

# Ensure config/env is loaded
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

API_ID = os.environ.get("TELEGRAM_API_ID")
API_HASH = os.environ.get("TELEGRAM_API_HASH")
PHONE = os.environ.get("TELEGRAM_PHONE")
BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "khoaha_bot")

async def main():
    if not API_ID or not API_HASH or not PHONE:
        print("\n❌ LỖI CẤU HÌNH USERBOT:")
        print("----------------------------------------------------------------------")
        print("Vui lòng thêm các thông số sau vào file '.env' trong thư mục dự án:")
        print("TELEGRAM_API_ID='1234567'")
        print("TELEGRAM_API_HASH='abcdef1234567890abcdef1234567890'")
        print("TELEGRAM_PHONE='+84xxxxxxxxx' (Số điện thoại đăng ký Telegram)")
        print("TELEGRAM_BOT_USERNAME='khoaha_bot' (Tên username của bot)")
        print("----------------------------------------------------------------------\n")
        return

    # Initialize Telethon Client
    session_path = Path("userbot")
    client = TelegramClient(str(session_path), int(API_ID), API_HASH)

    print("🤖 Đang kết nối tới Telegram...")
    await client.connect()

    # Check if authorized
    if not await client.is_user_authorized():
        if len(sys.argv) > 1 and sys.argv[1] == "login":
            print(f"🔑 Đang yêu cầu gửi mã xác minh tới số: {PHONE}")
            try:
                await client.send_code_request(PHONE)
                code = input("📥 Nhập mã xác minh (OTP) nhận được trên Telegram: ")
                try:
                    await client.sign_in(PHONE, code)
                except Exception as exc:
                    from telethon.errors import SessionPasswordNeededError
                    if isinstance(exc, SessionPasswordNeededError):
                        import getpass
                        try:
                            password = getpass.getpass("🔒 Tài khoản của bạn đã bật xác thực 2 lớp. Nhập mật khẩu 2 lớp: ")
                        except Exception:
                            password = input("🔒 Tài khoản của bạn đã bật xác thực 2 lớp. Nhập mật khẩu 2 lớp: ")
                        await client.sign_in(password=password)
                    else:
                        raise exc
                print("✅ Đăng nhập thành công! File session đã được lưu.")
            except Exception as e:
                print("❌ Đăng nhập thất bại:", e)
        else:
            print("❌ Chưa xác thực! Vui lòng mở terminal máy tính của bạn và chạy lệnh sau để đăng nhập:")
            print("python scripts/telegram_userbot.py login")
            await client.disconnect()
            return
    else:
        print("✅ Đã xác thực thành công.")

    # Process subcommands
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "send":
            if len(sys.argv) < 3:
                print("Lỗi: Thiếu nội dung tin nhắn. Sử dụng: send \"nội dung\"")
            else:
                msg = sys.argv[2]
                print(f"📨 Đang gửi tin nhắn tới @{BOT_USERNAME}...")
                await client.send_message(BOT_USERNAME, msg)
                print("✅ Đã gửi thành công!")
        elif cmd == "send_file":
            if len(sys.argv) < 3:
                print("Lỗi: Thiếu đường dẫn file. Sử dụng: send_file \"đường_dẫn\" [caption]")
            else:
                fpath = sys.argv[2]
                caption = sys.argv[3] if len(sys.argv) > 3 else ""
                if not os.path.exists(fpath):
                    print(f"❌ Lỗi: File không tồn tại tại {fpath}")
                else:
                    print(f"📨 Đang gửi file {os.path.basename(fpath)} tới @{BOT_USERNAME}...")
                    await client.send_file(BOT_USERNAME, fpath, caption=caption)
                    print("✅ Đã gửi file thành công!")
        elif cmd == "login":
            pass
        else:
            print(f"Lệnh không hợp lệ: {cmd}")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
