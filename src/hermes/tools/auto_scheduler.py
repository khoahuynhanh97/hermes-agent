"""
Auto scheduler for affiliate research pipeline.

Continuously checks crawl_rules.json for enabled scheduled runs and the
auto_run interval. When a scheduled run is due (or the interval elapses),
it invokes the auto_crawler to fetch products, write CSV, enqueue the job,
and run the worker.

Usage:
    python -m hermes.tools.auto_scheduler            # watch forever
    python -m hermes.tools.auto_scheduler --once     # single pass
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hermes.tools.crawl_rules import load_rules  # noqa: E402


def _parse_time(value: str) -> timedelta:
    """Parse 'HH:MM' into a timedelta since midnight."""
    hour, minute = (int(part) for part in value.split(":"))
    return timedelta(hours=hour, minutes=minute)


def _due(rules: dict, last_run_at: dict) -> dict | None:
    """Return the next scheduled run that is due, or None."""
    now = datetime.now()
    time_of_day = timedelta(hours=now.hour, minutes=now.minute)
    today_key = now.date().isoformat()

    for run in rules.get("scheduled_runs", []):
        if not run.get("enabled", False):
            continue
        name = run.get("name", "scheduled")
        last = last_run_at.get(name)
        if last == today_key:
            continue  # already ran today
        scheduled = _parse_time(run.get("time", "09:00"))
        if time_of_day >= scheduled:
            return run

    return None


def _interval_due(rules: dict, last_auto: datetime | None) -> bool:
    defaults = rules.get("defaults", {})
    if not defaults.get("auto_run", False):
        return False
    interval_minutes = int(defaults.get("auto_run_interval_minutes", 60))
    if last_auto is None:
        return True
    return (datetime.now() - last_auto) >= timedelta(minutes=interval_minutes)


def run_scheduler(*, once: bool = False, poll_seconds: float = 60.0) -> int:
    from hermes.tools.auto_crawler import run_once

    rules = load_rules()
    last_run_at: dict[str, str] = {}
    last_auto: datetime | None = None

    print("=== Hermes Auto Scheduler ===")
    print(f"Scheduled runs: {len(rules.get('scheduled_runs', []))}")
    print(f"Auto-run interval: {rules.get('defaults', {}).get('auto_run_interval_minutes', 60)} min")
    print(f"Polling every {poll_seconds:.0f}s. Ctrl+C to stop.\n")

    while True:
        try:
            rules = load_rules()  # reload in case config changed

            scheduled = _due(rules, last_run_at)
            if scheduled:
                name = scheduled.get("name", "scheduled")
                print(f"[SCHEDULE] Running '{name}' at {datetime.now().strftime('%H:%M:%S')}")
                try:
                    run_once(scheduled)
                except Exception as exc:
                    print(f"[ERROR] Scheduled run '{name}' failed: {exc}")
                last_run_at[name] = datetime.now().date().isoformat()

            if _interval_due(rules, last_auto):
                print(f"[AUTO] Interval run at {datetime.now().strftime('%H:%M:%S')}")
                try:
                    run_once(None)
                except Exception as exc:
                    print(f"[ERROR] Auto run failed: {exc}")
                last_auto = datetime.now()

            if once:
                break
            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            print("\nScheduler stopped.")
            return 0
        except Exception as exc:
            print(f"[ERROR] Scheduler loop: {exc}")
            if once:
                return 1
            time.sleep(poll_seconds)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one scheduler pass and exit")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    args = parser.parse_args(argv)
    return run_scheduler(once=args.once, poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
