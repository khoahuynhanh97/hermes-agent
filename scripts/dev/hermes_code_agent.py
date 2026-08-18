"""
Hermes coding-agent CLI.

Current mode: dry-run planning only. It does not apply patches.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hermes.application.core.coding_agent import CodingAgentPlanner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes coding-agent dry-run planner")
    parser.add_argument("request", nargs="*", help="Coding request")
    parser.add_argument("--message", "-m", default="", help="Coding request")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--write-report", action="store_true", help="Write Markdown report under reports/")
    parser.add_argument("--output", default="", help="Optional report output path")
    parser.add_argument("--limit", type=int, default=8, help="Max selected files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request = args.message or " ".join(args.request).strip()
    if not request:
        print("Usage: python scripts\\hermes_code_agent.py --message \"fix telegram duplicate reports\"")
        return 2

    planner = CodingAgentPlanner(REPO_ROOT)
    plan = planner.build_plan(request, limit=args.limit)

    if args.write_report or args.output:
        report_path = planner.write_report(plan, output_path=args.output or None)
        print(f"Report: {report_path}")

    if args.json:
        print(json.dumps(planner.to_dict(plan), ensure_ascii=False, indent=2))
    else:
        print(planner.format_markdown(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
