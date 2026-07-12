import requests
import urllib.parse
import re

query = "site:tiktok.com giá đỡ điện thoại"
url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote_plus(query)}"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
r = requests.get(url, headers=headers)
print(f"Status Code: {r.status_code}")
print(f"HTML Length: {len(r.text)}")
# print first 500 chars of body
print(r.text[:500])
