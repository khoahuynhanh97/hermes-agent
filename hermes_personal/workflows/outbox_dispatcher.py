from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from hermes_personal.workflows.outbox_repository import (
    OutboxClaim,
    OutboxRepository,
)


@dataclass
class DispatchReport:
    claimed: int
    succeeded: int
    failed: int
    quarantined: int


class OutboxDispatcher:
    def __init__(
        self,
        repository: OutboxRepository,
        delivery_fn: Callable[[str, str], None],
        worker_id: str = "worker-1",
        lease_duration_seconds: float = 30.0,
        backoff_base_seconds: float = 2.0,
        max_backoff_seconds: float = 300.0,
    ):
        self.repository = repository
        self.delivery_fn = delivery_fn
        self.worker_id = worker_id
        self.lease_duration_seconds = lease_duration_seconds
        self.backoff_base_seconds = backoff_base_seconds
        self.max_backoff_seconds = max_backoff_seconds

    def process_batch(
        self, batch_size: int = 10, now_iso: str | None = None
    ) -> DispatchReport:
        claims = self.repository.claim(
            self.worker_id, self.lease_duration_seconds, batch_size, now_iso
        )
        claimed_count = len(claims)
        succeeded = 0
        failed = 0
        quarantined = 0

        for claim in claims:
            try:
                self.delivery_fn(claim.workflow_id, claim.message)
                ack_success = self.repository.ack(
                    claim.outbox_id, claim.lease_token, self.worker_id, now_iso
                )
                if ack_success is True:
                    succeeded += 1
            except Exception as ex:
                status = self.repository.record_failure(
                    claim.outbox_id,
                    claim.lease_token,
                    self.worker_id,
                    str(ex),
                    self.backoff_base_seconds,
                    self.max_backoff_seconds,
                    now_iso,
                )
                if status == "quarantined":
                    quarantined += 1
                elif status in ("stale", "stale_lease"):
                    pass
                else:
                    failed += 1

        return DispatchReport(
            claimed=claimed_count,
            succeeded=succeeded,
            failed=failed,
            quarantined=quarantined,
        )

    def reclaim_expired(self, now_iso: str | None = None) -> int:
        return self.repository.reclaim_expired(now_iso)
