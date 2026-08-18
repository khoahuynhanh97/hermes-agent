"""Lightweight guard script to enforce repository layout policy."""
import json
import os
import sys
import fnmatch
from pathlib import Path

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    repo_root = Path(__file__).resolve().parents[2]
    policy_path = repo_root / "scripts" / "policies" / "repository-layout.json"
    
    if not policy_path.exists():
        print(f"Policy file not found at: {policy_path}")
        sys.exit(2)
        
    with open(policy_path, "r", encoding="utf-8") as f:
        policy = json.load(f)
        
    allowed_dirs = set(policy.get("allowed_root_directories", []))
    allowed_files = set(policy.get("allowed_root_files", []))
    forbidden_dirs = set(policy.get("forbidden_root_directories", []))
    forbidden_patterns = policy.get("forbidden_root_file_patterns", [])
    generated_root_ignores = {".pytest_cache", ".pytest-tmp"}
    
    violations = []
    
    # 1. Scan root entries
    for entry in repo_root.iterdir():
        rel_path = entry.relative_to(repo_root)
        name = entry.name
        if name in generated_root_ignores:
            continue

        if entry.is_dir():
            # Check directory allowlist
            if name not in allowed_dirs:
                violations.append({
                    "path": str(rel_path),
                    "violation": "Directory not in allowed root list",
                    "expected": "Remove from repository or move to HERMES_DATA_DIR / proper subdirectory"
                })
        else:
            # Check file allowlist
            if name not in allowed_files:
                # Apply forbidden patterns check
                matched_forbidden = False
                for pat in forbidden_patterns:
                    if fnmatch.fnmatch(name, pat):
                        violations.append({
                            "path": str(rel_path),
                            "violation": f"File matches forbidden root pattern: {pat}",
                            "expected": "Remove from repository root or place in allowed subdirectory"
                        })
                        matched_forbidden = True
                        break
                if not matched_forbidden:
                    violations.append({
                        "path": str(rel_path),
                        "violation": "File not in allowed root list",
                        "expected": "Remove from repository root or place in allowed subdirectory"
                    })
                    
    # 2. Check for production Python code outside src/hermes, tests, and scripts
    allowed_python_roots = set(policy.get("allowed_python_script_roots", []))
    allowed_python_roots.add("src")
    
    for entry in repo_root.iterdir():
        if entry.is_dir() and entry.name not in allowed_python_roots:
            # Skip hidden directories like .venv, .git, .superpowers etc.
            if entry.name.startswith("."):
                continue
            # Scan for .py files inside this directory
            for py_file in entry.rglob("*.py"):
                rel_py = py_file.relative_to(repo_root)
                violations.append({
                    "path": str(rel_py),
                    "violation": "Production Python code outside src/hermes directory",
                    "expected": "Move python code to src/hermes/"
                })
                
    # 3. Detect duplicate venv (venv/) or root node_modules
    for name in ["venv", "node_modules"]:
        if (repo_root / name).exists():
             violations.append({
                 "path": name,
                 "violation": f"Forbidden root directory: {name}",
                 "expected": "Remove duplicate environment / node_modules from repository root"
             })

    # Print results
    if violations:
        print(f"[STRUCTURE GUARD] Found {len(violations)} repository layout violations:")
        print("-" * 80)
        for v in violations:
            print(f"Path: {v['path']}")
            print(f"  Violation: {v['violation']}")
            print(f"  Expected:  {v['expected']}")
            print("-" * 80)
        sys.exit(1)
    else:
        print("[STRUCTURE GUARD] Repository structure is clean and locked.")
        sys.exit(0)

if __name__ == "__main__":
    main()
