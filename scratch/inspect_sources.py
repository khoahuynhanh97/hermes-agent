import json
import re

with open('c:/Work/Code/TIKTOK/podcast-ai-n8n-starter/workflows/podcast-ai-m1-m2-m3.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find the node named "Code: Feed List" or similar
nodes = data.get("nodes", [])
feed_node = None
for node in nodes:
    if "Feed List" in node.get("name", "") or "Code" in node.get("type", ""):
        # Check if it has the sources JS code
        js_code = node.get("parameters", {}).get("jsCode", "")
        if "sources" in js_code:
            feed_node = node
            break

if feed_node:
    js_code = feed_node["parameters"]["jsCode"]
    # Extract sources array
    # Looking for: const sources = [ ... ]
    match = re.search(r'const sources = \[(.*?)\];', js_code, re.DOTALL)
    if match:
        sources_content = match.group(1).strip()
        print("Raw sources found:")
        # We can clean it up and print line by line
        for line in sources_content.split('\n'):
            line = line.strip()
            if line:
                print(line)
    else:
        # Just print the JS code first 60 lines
        print("JS Code:")
        print(js_code[:1000])
else:
    print("Could not find Feed List node.")
