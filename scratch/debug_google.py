import requests
import re
import urllib.parse

query = "site:tiktok.com giá đỡ điện thoại"
url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
r = requests.get(url, headers=headers)
print(f"Status Code: {r.status_code}")
print(f"HTML Length: {len(r.text)}")

# Find all hrefs
hrefs = re.findall(r'href=["\'](.*?)["\']', r.text)
print(f"Found {len(hrefs)} hrefs total.")
for h in hrefs[:50]:
    print(f"Href: {h}")
