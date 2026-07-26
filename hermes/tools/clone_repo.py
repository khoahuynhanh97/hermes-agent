from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def clone_repo(repo_url: str, target_dir: str | Path, shallow: bool = True) -> bool:
    """Clone a git repository to the target directory.
    
    Args:
        repo_url: URL or local path of the repository to clone.
        target_dir: Target directory path.
        shallow: If True, perform a shallow clone (--depth 1).
    
    Returns:
        True if clone succeeded, False otherwise.
    """
    target = Path(target_dir)
    
    if target.exists():
        print("[!] Target directory already exists: {}".format(target))
        user_input = input("Overwrite? (y/N): ").strip().lower()
        if user_input != "y":
            print("Clone cancelled.")
            return False
        import shutil
        shutil.rmtree(target)
    
    target.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = ["git", "clone"]
    if shallow:
        cmd.extend(["--depth", "1"])
    cmd.extend([str(repo_url), str(target)])
    
    print("[+] Cloning {} -> {}".format(repo_url, target))
    print("    Command: {}".format(" ".join(cmd)))
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("[OK] Successfully cloned to {}".format(target))
        return True
    else:
        print("[FAIL] Clone failed: {}".format(result.stderr.strip()))
        return False


def clone_self(target_dir: str | Path = "f/prompt.chat") -> bool:
    """Clone the current repository to the target directory.
    
    Args:
        target_dir: Target directory path (default: f/prompt.chat).
    
    Returns:
        True if clone succeeded, False otherwise.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    return clone_repo(str(repo_root), target_dir)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Clone a repository using Hermes tooling.")
    parser.add_argument("--target", default="f/prompt.chat", help="Target directory")
    parser.add_argument("--url", default=None, help="Repo URL or local path (default: current repo)")
    parser.add_argument("--no-shallow", action="store_true", help="Full clone instead of shallow")
    
    args = parser.parse_args()
    
    repo_url = args.url or "."
    target = args.target
    
    success = clone_repo(repo_url, target, shallow=not args.no_shallow)
    sys.exit(0 if success else 1)