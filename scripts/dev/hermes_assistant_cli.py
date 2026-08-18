"""
Terminal entrypoint for Hermes Assistant.

Current scope:
- Classify user requests.
- Split multi-part requests into tasks.
- Print a safe execution plan.

This does not edit files yet. Real coding actions should be added behind an
explicit permission gate in a later job.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hermes.application.core.assistant_runtime import HermesAssistantRuntime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes Assistant terminal CLI")
    parser.add_argument("--message", "-m", default="", help="Single request to plan")
    parser.add_argument("--json", action="store_true", help="Print plan as JSON")
    parser.add_argument("--interactive", "-i", action="store_true", help="Start interactive shell")
    return parser.parse_args()


def print_plan(runtime: HermesAssistantRuntime, message: str, as_json: bool = False) -> None:
    plan = runtime.build_plan(message)
    if as_json:
        print(json.dumps(runtime.to_dict(plan), ensure_ascii=False, indent=2))
    else:
        print(runtime.format_markdown(plan))


def run_interactive(runtime: HermesAssistantRuntime, as_json: bool = False) -> int:
    print("Hermes Assistant CLI")
    print("Type a request. Use /exit to quit. Current mode: dry-plan only.")
    while True:
        try:
            message = input("hermes> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not message:
            continue
        if message in {"/exit", "exit", "quit"}:
            return 0
        print_plan(runtime, message, as_json=as_json)
    return 0


def main() -> int:
    args = parse_args()
    runtime = HermesAssistantRuntime(REPO_ROOT)
    if args.interactive or not args.message:
        return run_interactive(runtime, as_json=args.json)
    print_plan(runtime, args.message, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
