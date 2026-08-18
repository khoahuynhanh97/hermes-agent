import os

def get_installed_browsers():
    """
    Quét hệ thống Windows và trả về danh sách các trình duyệt khả dụng
    để người dùng chọn trích xuất Cookie phục vụ tải video.
    
    Returns:
        list: Danh sách các tên trình duyệt (ví dụ: ['chrome', 'edge', 'coccoc'])
    """
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    app_data = os.environ.get("APPDATA", "")
    
    # Định nghĩa các đường dẫn dữ liệu phổ biến của trình duyệt trên Windows
    paths = {
        "chrome": os.path.join(local_app_data, "Google", "Chrome", "User Data"),
        "edge": os.path.join(local_app_data, "Microsoft", "Edge", "User Data"),
        "brave": os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "User Data"),
        "coccoc": os.path.join(local_app_data, "CocCoc", "Browser", "User Data"),
        "firefox": os.path.join(app_data, "Mozilla", "Firefox", "Profiles"),
    }
    
    available = []
    for name, path in paths.items():
        if os.path.exists(path):
            available.append(name)
            
    # Mặc định thêm lựa chọn Không dùng cookie
    return available

if __name__ == "__main__":
    print("Trình duyệt khả dụng trên máy của bạn:")
    print(get_installed_browsers())
