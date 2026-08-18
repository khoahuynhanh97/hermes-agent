import os
import json

# Force JSON backend to avoid SQLite schema issues
os.environ['HERMES_STORAGE_BACKEND'] = 'json'

from hermes.application.core.knowledge_store import get_store

entries = get_store().list_entries()

output_path = r"C:\\Users\\ninak\\Desktop\\knowledge_export.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(entries, f, ensure_ascii=False, indent=2)
print(f"Exported {len(entries)} entries to {output_path}")
