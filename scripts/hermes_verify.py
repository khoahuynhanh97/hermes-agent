"""
Hermes verification runner CLI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.verification_runner import VerificationRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run allowlisted Hermes verification commands")
    parser.add_argument("commands", nargs="*", help="Command(s) to run")
    parser.add_argument("--command", "-c", action="append", default=[], help="Command to run")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout per command in seconds")
    parser.add_argument("--report", default="", help="Optional report output path")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    commands = list(args.command)
    if args.commands:
        commands.append(" ".join(args.commands))
    if not commands:
        print("Usage: python scripts\\hermes_verify.py --command \"python scripts\\hermes_repo_map.py build\"")
        return 2

    runner = VerificationRunner(REPO_ROOT, timeout_seconds=args.timeout)
    run = runner.run(commands, report_path=args.report or None)

    if args.json:
        print(json.dumps(runner.to_dict(run), ensure_ascii=False, indent=2))
    else:
        print(f"OK: {run.ok}")
        print(f"Report: {run.report_path}")
        for result in run.results:
            print(f"- {result.command} -> allowed={result.allowed} returncode={result.returncode} reason={result.reason}")
    return 0 if run.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
