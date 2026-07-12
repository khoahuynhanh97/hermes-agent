import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from core.keyword_generator import nlp_expand_keywords, extract_keywords_from_product_page
from providers.smart_crawler_provider import (
    parse_shopee_url,
    fetch_shopee_product_details,
    search_duckduckgo_urls,
    download_video_clean,
    apply_quality_filter,
    split_audio_video
)

def test_direction_1():
    print("\n=== TEST DIRECTION 1: DIRECT KEYWORD & NLP EXPANSION ===")
    query = "Giá đỡ điện thoại xoay gập màu trắng"
    print(f"[*] Query input: {query}")
    
    # NLP expansion
    res = nlp_expand_keywords(query)
    print("[+] Expanded Entities:")
    print(f"  - Product: {res.get('entities', {}).get('product')}")
    print(f"  - Features: {res.get('entities', {}).get('features')}")
    print(f"  - Color: {res.get('entities', {}).get('color')}")
    
    kws = res.get("vi", []) + res.get("en", []) + res.get("zh", [])
    print(f"[+] Keywords vi/en/zh generated: {kws[:5]}")
    
    # Test locally using an existing video file from Hermes project
    local_vid = os.path.abspath("projects/gia-do-dien-thoai-hinh-thu-xinh-dep/source_assets/vn-11110107-6v98x-mk5ai3f0f18g8e.16000081769863419.mp4")
    print(f"[*] Testing with local video file: {local_vid}")
    
    if os.path.exists(local_vid):
        # Copy to scratch folder to simulate download target
        import shutil
        output_dir = os.path.abspath("./scratch_test_downloads")
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, "test_h1_local_review.mp4")
        shutil.copy2(local_vid, filepath)
        
        print(f"[+] Local video copied to: {filepath}")
        
        # Run Quality Gate
        passed = apply_quality_filter(filepath)
        print(f"  -> Quality Filter result: {'PASSED' if passed else 'REJECTED/DELETED'}")
        
        # Run AV Split if still exists
        if passed and os.path.exists(filepath):
            audio_dir = os.path.abspath("./scratch_test_downloads/audio")
            clips_dir = os.path.abspath("./scratch_test_downloads/clips")
            silent_vid, audio_file = split_audio_video(filepath, audio_dir, clips_dir)
            print(f"  -> Split result:")
            print(f"     Silent Video: {silent_vid}")
            print(f"     Audio Track: {audio_file}")
    else:
        print(f"[!] Local test video does not exist at: {local_vid}")

def test_direction_2():
    print("\n=== TEST DIRECTION 2: PRODUCT URL PARSING ===")
    shopee_url = "https://shopee.vn/Micro-thu-%C3%A2m-kh%C3%B4ng-d%C3%A2y-c%C3%A0i-%C3%A1o-mini-l%E1%BB%8Dc-ti%E1%BA%BFng-%E1%BB%93n-pin-8h-freeship-i.12345.67890"
    print(f"[*] Parsing Shopee URL: {shopee_url}")
    shop_id, item_id = parse_shopee_url(shopee_url)
    print(f"[+] Parsed: Shop ID = {shop_id} | Item ID = {item_id}")
    
    # Test extract keywords from mock title
    title = "Micro thu âm không dây cài áo mini lọc tiếng ồn pin 8h freeship"
    desc = "Microphone thu âm cài áo chuyên nghiệp lọc tiếng ồn hiệu quả khoảng cách 20m pin trâu 8 tiếng."
    print(f"[*] Extracting core keywords from title: '{title}'")
    res = extract_keywords_from_product_page(title, desc)
    print(f"[+] Core keywords vi: {res.get('vi')}")
    print(f"[+] Core keywords en: {res.get('en')}")
    print(f"[+] Core keywords zh: {res.get('zh')}")

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    test_direction_1()
    test_direction_2()
