import os
import json
import tempfile
import dotenv

dotenv.load_dotenv(override=True)

from tools.crawler import resolve_tiktok_media

test_urls = [
    "https://vt.tiktok.com/ZSXC78qkc",
    "https://vt.tiktok.com/ZSXj5n5xD",
    "https://vt.tiktok.com/ZSXuDRN8H",
    "https://vt.tiktok.com/ZSXgUWG1D",
    "https://vt.tiktok.com/ZSXgWqTX4"
]

tmp_dir = tempfile.mkdtemp()
for url in test_urls:
    print(f"\n--- Resolving: {url} ---")
    try:
        res = resolve_tiktok_media(url, output_dir=tmp_dir)
        print(f"  Source Kind: {res.source_kind}")
        print(f"  Confidence: {res.confidence}")
        print(f"  Error: {res.error}")
        print(f"  Media Paths ({len(res.media_paths)}): {[str(p) for p in res.media_paths]}")
        print(f"  Metadata Title: {res.metadata.get('title') if res.metadata else 'N/A'}")
    except Exception as e:
        print(f"  Exception resolving {url}: {e}")
