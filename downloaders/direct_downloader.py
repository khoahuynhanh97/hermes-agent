import os
import requests

def download_direct(url, output_path, log_callback=None):
    """
    Downloads a file directly from a URL using requests.
    Supports a log_callback for real-time status reporting.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        log(f"[*] Bắt đầu tải trực tiếp: {url}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with requests.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            with open(output_path, 'wb') as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and downloaded % (1024 * 1024) == 0:
                            percent = (downloaded / total_size) * 100
                            log(f"    - Đã tải {downloaded / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB ({percent:.1f}%)")
                            
        log(f"[+] Tải thành công: {output_path}")
        return True
    except Exception as e:
        log(f"[x] Lỗi khi tải trực tiếp URL: {e}")
        return False
