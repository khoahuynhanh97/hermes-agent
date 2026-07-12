"""
Hermes patch executor CLI.

Default mode is check-only. Use --apply only after reviewing the patch.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.patch_executor import PatchExecutor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate or apply a unified diff safely")
    parser.add_argument("patch_file", help="Unified diff patch file")
    parser.add_argument("--apply", action="store_true", help="Apply the patch after validation")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    parser.add_argument("--report", default="", help="Optional report output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    patch_path = Path(args.patch_file)
    if not patch_path.exists():
        print(f"Patch file not found: {patch_path}")
        return 2

    patch_text = patch_path.read_text(encoding="utf-8")
    executor = PatchExecutor(REPO_ROOT)
    result = executor.execute(patch_text, apply=args.apply, report_path=args.report or None)

    if args.json:
        print(json.dumps(result_to_dict(result), ensure_ascii=False, indent=2))
    else:
        print(f"OK: {result.ok}")
        print(f"Applied: {result.applied}")
        print(f"Report: {result.report_path}")
        if result.stderr.strip():
            print(result.stderr.strip())
    return 0 if result.ok else 1


def result_to_dict(result) -> dict:
    return {
        "ok": result.ok,
        "applied": result.applied,
        "checked_paths": result.checked_paths,
        "decisions": [decision.__dict__ for decision in result.decisions],
        "stdout": result.stdout,
        "stderr": result.stderr,
        "report_path": result.report_path,
    }


if __name__ == "__main__":
    raise SystemExit(main())
