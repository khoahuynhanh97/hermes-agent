import json
with open('c:/Work/Code/TIKTOK/podcast-ai-n8n-starter/workflows/podcast-ai-m1-m2-m3.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print("Settings keys:", data.get("settings", {}).keys())
print("Settings content:", data.get("settings", {}))
