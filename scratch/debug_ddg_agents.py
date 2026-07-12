import requests
import urllib.parse
import re

query = "site:tiktok.com giá đỡ điện thoại"
url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"

agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
]

for idx, ua in enumerate(agents):
    headers = {"User-Agent": ua}
    r = requests.get(url, headers=headers, timeout=10)
    print(f"Agent {idx+1}: Status {r.status_code}, Length: {len(r.text)}")
    if r.status_code == 200:
        links = re.findall(r'uddg=([^&"\'\s>]+)', r.text)
        print(f"   Found {len(links)} links!")
        if links:
            print(f"   First link: {urllib.parse.unquote(links[0])}")
            break
