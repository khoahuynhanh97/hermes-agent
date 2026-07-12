"""Quick test script to verify Crawler v2.1 upgrades import successfully."""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

print("="*60)
print("  HERMES v2.1 - CRAWLER & DOWNLOADER VERIFICATION")
print("="*60)

errors = []

# 1. smart_crawler_provider imports and functions
print("\n[1] Testing smart_crawler_provider.py...")
try:
    from providers.smart_crawler_provider import (
        get_browser_cookies,
        fetch_shopee_product_details,
        download_video_clean,
    )
    print("    [OK] get_browser_cookies imported successfully.")
    print("    [OK] fetch_shopee_product_details imported successfully.")
    print("    [OK] download_video_clean imported successfully.")
    
    # Check signatures
    import inspect
    sig_fetch = inspect.signature(fetch_shopee_product_details)
    sig_dl = inspect.signature(download_video_clean)
    print(f"    - fetch_shopee_product_details signature: {sig_fetch}")
    print(f"    - download_video_clean signature: {sig_dl}")
    
    if 'browser_cookies' in sig_fetch.parameters:
        print("    [OK] fetch_shopee_product_details supports browser_cookies.")
    else:
        errors.append("fetch_shopee_product_details missing browser_cookies parameter")
        
    if 'vertical_only' in sig_dl.parameters:
        print("    [OK] download_video_clean supports vertical_only.")
    else:
        errors.append("download_video_clean missing vertical_only parameter")
except Exception as e:
    errors.append(f"smart_crawler_provider import failed: {e}")
    print(f"    [FAIL] {e}")

# 2. shopee_search_provider imports
print("\n[2] Testing shopee_search_provider.py...")
try:
    from providers.shopee_search_provider import search_and_download_shopee
    print("    [OK] search_and_download_shopee imported successfully.")
    
    sig = inspect.signature(search_and_download_shopee)
    print(f"    - search_and_download_shopee signature: {sig}")
    if 'browser_cookies' in sig.parameters:
        print("    [OK] search_and_download_shopee supports browser_cookies.")
    else:
        errors.append("search_and_download_shopee missing browser_cookies parameter")
except Exception as e:
    errors.append(f"shopee_search_provider import failed: {e}")
    print(f"    [FAIL] {e}")

# 3. social_search_provider imports
print("\n[3] Testing social_search_provider.py...")
try:
    from providers.social_search_provider import search_and_download_social
    print("    [OK] search_and_download_social imported successfully.")
    
    sig = inspect.signature(search_and_download_social)
    print(f"    - search_and_download_social signature: {sig}")
    if 'vertical_only' in sig.parameters:
        print("    [OK] search_and_download_social supports vertical_only.")
    else:
        errors.append("search_and_download_social missing vertical_only parameter")
except Exception as e:
    errors.append(f"social_search_provider import failed: {e}")
    print(f"    [FAIL] {e}")

# 4. GUI check
print("\n[4] Testing GUI app.py syntax check again...")
try:
    import ast
    ast.parse(open('gui/app.py', encoding='utf-8').read())
    print("    [OK] gui/app.py compiles cleanly.")
except Exception as e:
    errors.append(f"gui/app.py syntax check failed: {e}")
    print(f"    [FAIL] {e}")

# Summary
print("\n" + "="*60)
if errors:
    print(f"RESULT: {len(errors)} TESTS FAILED!")
    for err in errors:
        print(f"  - {err}")
else:
    print("RESULT: ALL CRAWLER v2.1 TESTS PASSED!")
print("="*60)
sys.exit(len(errors))
