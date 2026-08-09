import os
import sys
import sqlite3

appdata = os.path.expandvars(r'%LOCALAPPDATA%\hermes')
canonical_repo = r'd:\work\hermes-agent'
data_root = r'd:\work\hermes-agent-data'

print("=== 1. Inspecting config.yaml ===")
cfg_path = os.path.join(appdata, 'config.yaml')
if os.path.exists(cfg_path):
    size = os.path.getsize(cfg_path)
    print(f"  config.yaml exists (size: {size} bytes)")
    with open(cfg_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    print("  First 15 lines of config.yaml:")
    for line in lines[:15]:
        print("    ", line.rstrip())
else:
    print("  config.yaml DOES NOT EXIST")

print("\n=== 2. Inspecting .env in AppData vs Repo ===")
env_path = os.path.join(appdata, '.env')
repo_env_path = os.path.join(canonical_repo, '.env')
print("  AppData .env exists:", os.path.exists(env_path))
print("  Repo .env exists   :", os.path.exists(repo_env_path))
if os.path.exists(repo_env_path):
    print("  Repo .env size     :", os.path.getsize(repo_env_path), "bytes")
if os.path.exists(env_path):
    print("  AppData .env size  :", os.path.getsize(env_path), "bytes")

print("\n=== 3. Inspecting state.db in AppData ===")
db_path = os.path.join(appdata, 'state.db')
if os.path.exists(db_path):
    print(f"  state.db size: {os.path.getsize(db_path)} bytes")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print("  Tables in state.db:", tables)
        for t in tables:
            cursor.execute(f'SELECT COUNT(*) FROM "{t}";')
            count = cursor.fetchone()[0]
            print(f"    Table {t}: {count} rows")
        conn.close()
    except Exception as e:
        print("  Error reading state.db:", e)

print("\n=== 4. Inspecting sessions/ ===")
sessions_dir = os.path.join(appdata, 'sessions')
if os.path.exists(sessions_dir):
    items = os.listdir(sessions_dir)
    print(f"  sessions/ count: {len(items)}")
    for item in items[:10]:
        print("    ", item)

print("\n=== 5. Inspecting memories/ ===")
mem_dir = os.path.join(appdata, 'memories')
if os.path.exists(mem_dir):
    items = os.listdir(mem_dir)
    print(f"  memories/ count: {len(items)}")
    for item in items[:10]:
        print("    ", item)

print("\n=== 6. Inspecting skills/ in AppData vs Repo ===")
app_skills_dir = os.path.join(appdata, 'skills')
repo_skills_dir = os.path.join(canonical_repo, 'skills')
app_skills = set(os.listdir(app_skills_dir)) if os.path.exists(app_skills_dir) else set()
repo_skills = set(os.listdir(repo_skills_dir)) if os.path.exists(repo_skills_dir) else set()
print("  Skills only in AppData:", sorted(list(app_skills - repo_skills)))
print("  Skills in both        :", sorted(list(app_skills & repo_skills)))
print("  Skills only in Repo   :", sorted(list(repo_skills - app_skills)))

print("\n=== 7. All Top-Level Items in %LOCALAPPDATA%\\hermes ===")
for item in sorted(os.listdir(appdata)):
    p = os.path.join(appdata, item)
    if os.path.isfile(p):
        print(f"  [File] {item} ({os.path.getsize(p)} bytes)")
    elif os.path.isdir(p):
        print(f"  [Dir ] {item}/")
