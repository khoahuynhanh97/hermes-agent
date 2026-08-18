from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from hermes.application.core.affiliate_research_jobs import (  # noqa: E402
    AffiliateResearchJobWorker,
    build_affiliate_research_job_handler,
)
from hermes.jobs import JobRepository  # noqa: E402


def build_worker() -> AffiliateResearchJobWorker:
    jobs = JobRepository()
    jobs.recover_interrupted()
    return AffiliateResearchJobWorker(jobs, build_affiliate_research_job_handler())


def run_worker(
    worker: AffiliateResearchJobWorker,
    *,
    once: bool = False,
    poll_seconds: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    while True:
        processed = worker.process_next_job()
        if once:
            return 0
        if not processed:
            sleep(poll_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the dedicated affiliate product research queue worker."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one available affiliate job and exit.",
    )
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args(argv)
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be greater than zero")
    return run_worker(
        build_worker(), once=args.once, poll_seconds=args.poll_seconds
    )


if __name__ == "__main__":
    raise SystemExit(main())
