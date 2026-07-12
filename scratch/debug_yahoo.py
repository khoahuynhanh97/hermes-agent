import requests
import urllib.parse
import re

query = "site:douyin.com/video giá đỡ điện thoại xoay"
url = f"https://search.yahoo.com/search?q={urllib.parse.quote_plus(query)}"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
r = requests.get(url, headers=headers)
print(f"Status Code: {r.status_code}")
print(f"HTML Length: {len(r.text)}")

# Find all links containing douyin.com
links = re.findall(r'href=["\'](https?://r\.search\.yahoo\.com/[^\s"\']*)', r.text)
print(f"Found {len(links)} Yahoo redirect links.")
count = 0
for l in links:
    cleaned = urllib.parse.unquote(l)
    if "douyin.com" in cleaned:
        # Extract real url
        m = re.search(r'RU=(https?://[^\s&]+)', cleaned)
        if m:
            print(f"Douyin URL: {m.group(1)}")
            count += 1
            if count >= 10:
                break
