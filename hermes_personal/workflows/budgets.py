from __future__ import annotations

import dataclasses
from typing import Dict, List


class BudgetError(Exception):
    """Raised for budget violations."""


@dataclasses.dataclass(frozen=True)
class BudgetPolicy:
    max_total: int
    per_channel: Dict[str, int]


@dataclasses.dataclass
class BudgetAllocation:
    channel: str
    amount: int
    idempotency_key: str | None = None
    _committed: bool = dataclasses.field(default=False, init=False)


class BudgetEngine:
    def __init__(self, policy: BudgetPolicy):
        self.policy = policy
        self._allocated: Dict[str, int] = {}
        self._pending: List[BudgetAllocation] = []
        # Track checks without reservation to enforce cumulative total limits
        self._checked_total: int = 0
        self._checked_channel: Dict[str, int] = {}
        # Track committed idempotency keys to avoid double commits
        self._committed_keys: set[str] = set()

    def _total_allocated(self) -> int:
        return sum(self._allocated.values()) + sum(a.amount for a in self._pending)

    def check_budget(self, channel: str, amount: int) -> None:
        if amount <= 0:
            raise BudgetError("amount must be positive")
        channel_limit = self.policy.per_channel.get(channel, self.policy.max_total)
        channel_used = (
            self._allocated.get(channel, 0)
            + sum(a.amount for a in self._pending if a.channel == channel)
            + self._checked_channel.get(channel, 0)
        )
        if channel_used + amount > channel_limit:
            raise BudgetError(f"channel '{channel}' exceeds its limit")
        # Include previously checked amounts in total limit calculation
        if self._total_allocated() + self._checked_total + amount > self.policy.max_total:
            raise BudgetError("total budget exceeds max_total")
        # Record this check for future cumulative checks
        self._checked_total += amount
        self._checked_channel[channel] = self._checked_channel.get(channel, 0) + amount

    def reserve_budget(self, channel: str, amount: int, idempotency_key: str | None = None) -> BudgetAllocation:
        self.check_budget(channel, amount)
        alloc = BudgetAllocation(channel=channel, amount=amount, idempotency_key=idempotency_key)
        self._pending.append(alloc)
        return alloc

    def commit_budget(self, allocation: BudgetAllocation) -> None:
        if allocation not in self._pending:
            raise BudgetError("allocation not pending")
        # Idempotency: if already committed for this key, ignore
        key = allocation.idempotency_key
        if key and key in self._committed_keys:
            if allocation in self._pending:
                self._pending.remove(allocation)
            return
        self._pending.remove(allocation)
        self._allocated[allocation.channel] = self._allocated.get(allocation.channel, 0) + allocation.amount
        allocation._committed = True
        if key:
            self._committed_keys.add(key)

    def release_budget(self, allocation: BudgetAllocation) -> None:
        if allocation not in self._pending:
            raise BudgetError("allocation not pending")
        self._pending.remove(allocation)

    def get_allocated(self, channel: str | None = None) -> dict[str, int] | int:
        if channel:
            return self._allocated.get(channel, 0)
        return dict(self._allocated)


# Convenience functions operating on a default engine (optional)
_default_engine: BudgetEngine | None = None


def init_default_engine(policy: BudgetPolicy) -> BudgetEngine:
    global _default_engine
    _default_engine = BudgetEngine(policy)
    return _default_engine


def check_budget(channel: str, amount: int) -> None:
    if _default_engine is None:
        raise BudgetError("default engine not initialized")
    _default_engine.check_budget(channel, amount)


def reserve_budget(channel: str, amount: int, idempotency_key: str | None = None) -> BudgetAllocation:
    if _default_engine is None:
        raise BudgetError("default engine not initialized")
    return _default_engine.reserve_budget(channel, amount, idempotency_key)


def commit_budget(allocation: BudgetAllocation) -> None:
    if _default_engine is None:
        raise BudgetError("default engine not initialized")
    _default_engine.commit_budget(allocation)


def release_budget(allocation: BudgetAllocation) -> None:
    if _default_engine is None:
        raise BudgetError("default engine not initialized")
    _default_engine.release_budget(allocation)


def get_allocated_budget(channel: str | None = None) -> dict[str, int] | int:
    if _default_engine is None:
        return 0 if channel else {}
    return _default_engine.get_allocated(channel)
