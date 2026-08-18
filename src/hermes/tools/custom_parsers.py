import re
import os
import requests

def extract_ecommerce_video(url):
    """
    Trích xuất link video trực tiếp (MP4) từ mã nguồn HTML của các trang TMĐT 
    như 1688, JD, Taobao, Tmall, Pinduoduo khi yt-dlp không hỗ trợ sẵn.
    
    Args:
        url (str): Đường dẫn link trang sản phẩm.
        
    Returns:
        str: Link video MP4 trực tiếp, hoặc None nếu không tìm thấy.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        # Tải trang HTML
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code != 200:
            return None
            
        html = response.text
        
        # Biểu thức chính quy tìm các liên kết MP4 (hỗ trợ cả link không có giao thức //)
        mp4_pattern = r'(https?:)?//[a-zA-Z0-9_\-\./%]+\.mp4'
        matches = re.finditer(mp4_pattern, html)
        
        valid_urls = []
        for match in matches:
            full_match = match.group(0)
            if full_match.startswith('//'):
                full_match = 'https:' + full_match
            elif not full_match.startswith('http'):
                full_match = 'https://' + full_match
                
            if full_match not in valid_urls:
                valid_urls.append(full_match)
                
        # Ưu tiên các tên miền video đặc trưng của các sàn lớn
        priority_domains = [
            "video.m.1688.com",   # 1688
            "360buyimg.com",      # JD (Jingdong)
            "cloud.video.taobao", # Taobao
            "pinduoduo.com",      # Pinduoduo
            "alicdn.com"          # Alibaba Cloud CDN
        ]
        
        for domain in priority_domains:
            for vurl in valid_urls:
                if domain in vurl:
                    return vurl
                    
        # Nếu không trích xuất được tên miền ưu tiên, lấy link mp4 đầu tiên
        if valid_urls:
            return valid_urls[0]
            
    except Exception as e:
        print(f"[!] Lỗi khi cào link video sản phẩm trực tiếp: {e}")
        
    return None

def download_direct_mp4(mp4_url, output_path):
    """Tải trực tiếp file MP4 bằng requests để tăng tốc độ và bảo đảm thành công"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        print(f"[*] Bắt đầu tải trực tiếp MP4 từ: {mp4_url}")
        with requests.get(mp4_url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"[+] Đã tải trực tiếp thành công: {output_path}")
        return True
    except Exception as e:
        print(f"[x] Lỗi tải trực tiếp MP4: {e}")
        return False
