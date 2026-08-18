"""Clean generated test directories and cache artifacts."""
import os
import shutil
from pathlib import Path

REPO_ROOT = Path(r"D:\work\hermes-agent").resolve()

def clean():
    prefixes = [
        ".pytest-",
        ".tmp-",
        ".audit-pytest-",
        "workhermes-agent.tmp-",
    ]
    exact = [
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".coverage",
        "htmlcov",
    ]

    for item in list(REPO_ROOT.iterdir()):
        if item.is_dir():
            if item.name in exact or any(item.name.startswith(p) for p in prefixes):
                print(f"Deleting directory: {item.name}")
                try:
                    shutil.rmtree(item, ignore_errors=True)
                except Exception as e:
                    print(f"Error removing {item.name}: {e}")

    # Remove all __pycache__ and *.pyc
    for pycache in list(REPO_ROOT.rglob("__pycache__")):
        if ".venv" not in pycache.parts and "node_modules" not in pycache.parts:
            shutil.rmtree(pycache, ignore_errors=True)

    for pyc in list(REPO_ROOT.rglob("*.py[cod]")):
        if ".venv" not in pyc.parts and "node_modules" not in pyc.parts:
            try:
                pyc.unlink()
            except Exception:
                pass

if __name__ == "__main__":
    clean()
    print("Cleanup completed.")
