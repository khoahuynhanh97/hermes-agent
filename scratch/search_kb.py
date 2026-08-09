import os
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("=== ALL KNOWLEDGE BASE UNIFIED INDEX ENTRIES ===")
with open('knowledge_base/unified_index.json', 'r', encoding='utf-8') as f:
    idx = json.load(f)
    for entry in idx.get('entries', []):
        print(f"[{entry.get('status').upper()}] {entry.get('title')} ({entry.get('slug')})")
        if 'summary' in entry:
            print(f"  Summary: {entry['summary'][:150]}")
        print(f"  Detail file: {entry.get('detail_file')}")

print("\n=== ALL PROJECT PROPOSALS & METADATA ===")
for d in os.listdir('projects'):
    dp = os.path.join('projects', d)
    if os.path.isdir(dp):
        for root, dirs, files in os.walk(dp):
            for f in files:
                if f == 'proposal_meta.json':
                    try:
                        with open(os.path.join(root, f), 'r', encoding='utf-8') as pf:
                            meta = json.load(pf)
                            print(f"Project: {d} | Title: {meta.get('title')}")
                            print(f"  Tools: {meta.get('tools_and_concepts')}")
                    except Exception:
                        pass
