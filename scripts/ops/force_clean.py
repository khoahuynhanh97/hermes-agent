import os
import stat
import shutil
from pathlib import Path

REPO_ROOT = Path(r"D:\work\hermes-agent").resolve()

def make_writable_and_remove(top_dir: Path):
    for root, dirs, files in os.walk(top_dir, topdown=False):
        for name in files:
            file_path = os.path.join(root, name)
            try:
                os.chmod(file_path, stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH | stat.S_IWRITE)
                os.remove(file_path)
            except Exception as e:
                pass
        for name in dirs:
            dir_path = os.path.join(root, name)
            try:
                os.chmod(dir_path, stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH | stat.S_IWRITE)
                os.rmdir(dir_path)
            except Exception as e:
                pass
    try:
        os.chmod(top_dir, stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH | stat.S_IWRITE)
        top_dir.rmdir()
        print(f"Successfully removed: {top_dir.name}")
    except Exception as e:
        print(f"Failed to remove top directory {top_dir.name}: {e}")

def main():
    prefixes = [".pytest-", ".tmp-", ".audit-pytest-", "workhermes-agent.tmp-"]
    exact = [".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage", "htmlcov"]
    
    for item in list(REPO_ROOT.iterdir()):
        if item.is_dir():
            if item.name in exact or any(item.name.startswith(p) for p in prefixes):
                make_writable_and_remove(item)

if __name__ == "__main__":
    main()
