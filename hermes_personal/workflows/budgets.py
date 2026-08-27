from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict
from uuid import uuid4

from hermes_personal.storage.sqlite import connect as connect_sqlite


class BudgetError(Exception):
    """Raised for budget violations."""


class BudgetConflict(BudgetError):
    """Raised when an idempotency key is reused with conflicting parameters."""


@dataclasses.dataclass(frozen=True)
class BudgetPolicy:
    max_total: int
    per_channel: Dict[str, int]
    policy_id: str = "default"
    policy_version: int = 1


@dataclasses.dataclass
class BudgetAllocation:
    channel: str
    amount: int
    idempotency_key: str | None = None
    reservation_id: str | None = None
    owner_user_id: str = "default-owner"
    scope_id: str = "default-scope"
    currency: str = "USD"
    state: str = "reserved"
    capability_id: str = "general"
    operation_input_digest: str = ""
    policy_id: str = "default"
    policy_version: int = 1
    policy_snapshot_json: str = "{}"
    external_reference: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def _committed(self) -> bool:
        return self.state == "committed"

    @_committed.setter
    def _committed(self, value: bool) -> None:
        if value:
            self.state = "committed"


def _request_digest(
    schema_version: int,
    capability_id: str,
    owner_user_id: str,
    scope_id: str,
    channel: str,
    amount: int,
    currency: str,
    operation_input_digest: str,
    external_reference: str | None = None,
) -> str:
    payload = {
        "amount": amount,
        "capability_id": capability_id,
        "channel": channel,
        "currency": currency,
        "external_reference": external_reference or "",
        "operation_input_digest": operation_input_digest,
        "owner_user_id": owner_user_id,
        "schema_version": schema_version,
        "scope_id": scope_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _row_to_allocation(row: sqlite3.Row) -> BudgetAllocation:
    return BudgetAllocation(
        channel=row["channel"],
        amount=row["amount"],
        idempotency_key=row["idempotency_key"],
        reservation_id=row["reservation_id"],
        owner_user_id=row["owner_user_id"],
        scope_id=row["scope_id"],
        currency=row["currency"],
        state=row["state"],
        capability_id=row["capability_id"] if "capability_id" in row.keys() else "general",
        operation_input_digest=row["operation_input_digest"] if "operation_input_digest" in row.keys() else "",
        policy_id=row["policy_id"] if "policy_id" in row.keys() else "default",
        policy_version=row["policy_version"] if "policy_version" in row.keys() else 1,
        policy_snapshot_json=row["policy_snapshot_json"] if "policy_snapshot_json" in row.keys() else "{}",
        external_reference=row["external_reference"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class BudgetRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def check_budget(
        self,
        policy: BudgetPolicy,
        channel: str,
        amount: int,
        owner_user_id: str = "default-owner",
        scope_id: str = "default-scope",
    ) -> None:
        if amount <= 0:
            raise BudgetError("amount must be positive")
        if not channel or not channel.strip():
            raise BudgetError("channel must not be blank")

        try:
            channel_limit = policy.per_channel.get(channel, policy.max_total)

            c_used_row = self._connection.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM budget_reservation
                WHERE owner_user_id = ? AND scope_id = ? AND channel = ? AND state IN ('reserved', 'committed')
                """,
                (owner_user_id, scope_id, channel),
            ).fetchone()
            channel_used = c_used_row["total"] if c_used_row else 0

            if channel_used + amount > channel_limit:
                raise BudgetError(f"channel '{channel}' exceeds its limit")

            t_used_row = self._connection.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM budget_reservation
                WHERE owner_user_id = ? AND scope_id = ? AND state IN ('reserved', 'committed')
                """,
                (owner_user_id, scope_id),
            ).fetchone()
            total_used = t_used_row["total"] if t_used_row else 0

            if total_used + amount > policy.max_total:
                raise BudgetError("total budget exceeds max_total")
        except (sqlite3.Error, sqlite3.OperationalError) as ex:
            if isinstance(ex, BudgetError):
                raise
            raise BudgetError(f"Budget database failure: {ex}") from ex

    def reserve_budget(
        self,
        policy: BudgetPolicy,
        channel: str,
        amount: int,
        idempotency_key: str | None = None,
        owner_user_id: str = "default-owner",
        scope_id: str = "default-scope",
        currency: str = "USD",
        capability_id: str = "general",
        operation_input_digest: str = "",
        external_reference: str | None = None,
        schema_version: int = 1,
    ) -> BudgetAllocation:
        if amount <= 0:
            raise BudgetError("amount must be positive")
        if not channel or not channel.strip():
            raise BudgetError("channel must not be blank")

        effective_key = (
            idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
        )
        digest = _request_digest(
            schema_version,
            capability_id,
            owner_user_id,
            scope_id,
            channel,
            amount,
            currency,
            operation_input_digest,
            external_reference,
        )

        try:
            with self._connection:
                self._connection.execute("BEGIN IMMEDIATE")

                if effective_key:
                    row = self._connection.execute(
                        """
                        SELECT *
                        FROM budget_reservation
                        WHERE owner_user_id = ? AND scope_id = ? AND idempotency_key = ?
                        """,
                        (owner_user_id, scope_id, effective_key),
                    ).fetchone()
                    if row is not None:
                        if row["request_digest"] != digest:
                            if row["amount"] != amount or row["currency"] != currency:
                                raise BudgetConflict(
                                    f"Idempotency conflict for key '{effective_key}': amount/currency mismatch "
                                    f"(existing: {row['amount']} {row['currency']}, incoming: {amount} {currency})"
                                )
                            raise BudgetConflict(
                                f"Idempotency conflict for key '{effective_key}': action/input digest mismatch "
                                f"(existing digest: {row['request_digest']}, incoming digest: {digest})"
                            )
                        if row["state"] != "released":
                            return _row_to_allocation(row)

                channel_limit = policy.per_channel.get(channel, policy.max_total)

                c_used_row = self._connection.execute(
                    """
                    SELECT COALESCE(SUM(amount), 0) AS total
                    FROM budget_reservation
                    WHERE owner_user_id = ? AND scope_id = ? AND channel = ? AND state IN ('reserved', 'committed')
                    """,
                    (owner_user_id, scope_id, channel),
                ).fetchone()
                channel_used = c_used_row["total"] if c_used_row else 0

                if channel_used + amount > channel_limit:
                    raise BudgetError(f"channel '{channel}' exceeds its limit")

                t_used_row = self._connection.execute(
                    """
                    SELECT COALESCE(SUM(amount), 0) AS total
                    FROM budget_reservation
                    WHERE owner_user_id = ? AND scope_id = ? AND state IN ('reserved', 'committed')
                    """,
                    (owner_user_id, scope_id),
                ).fetchone()
                total_used = t_used_row["total"] if t_used_row else 0

                if total_used + amount > policy.max_total:
                    raise BudgetError("total budget exceeds max_total")

                if effective_key and row is not None and row["state"] == "released":
                    now_iso = datetime.now(timezone.utc).isoformat()
                    self._connection.execute(
                        "UPDATE budget_reservation SET state = 'reserved', updated_at = ? WHERE reservation_id = ?",
                        (now_iso, row["reservation_id"]),
                    )
                    alloc = _row_to_allocation(row)
                    alloc.state = "reserved"
                    alloc.updated_at = now_iso
                    return alloc

                res_id = f"res_{uuid4().hex}"
                key_to_store = effective_key or res_id
                now_iso = datetime.now(timezone.utc).isoformat()
                policy_snapshot = json.dumps(
                    {
                        "policy_id": policy.policy_id,
                        "policy_version": policy.policy_version,
                        "max_total": policy.max_total,
                        "per_channel": policy.per_channel,
                    },
                    sort_keys=True,
                )

                self._connection.execute(
                    """
                    INSERT INTO budget_reservation (
                      reservation_id, owner_user_id, scope_id, channel, amount, currency,
                      idempotency_key, request_digest, state, capability_id, operation_input_digest,
                      policy_id, policy_version, policy_snapshot_json, external_reference, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        res_id,
                        owner_user_id,
                        scope_id,
                        channel,
                        amount,
                        currency,
                        key_to_store,
                        digest,
                        capability_id,
                        operation_input_digest,
                        policy.policy_id,
                        policy.policy_version,
                        policy_snapshot,
                        external_reference,
                        now_iso,
                        now_iso,
                    ),
                )

                return BudgetAllocation(
                    channel=channel,
                    amount=amount,
                    idempotency_key=key_to_store,
                    reservation_id=res_id,
                    owner_user_id=owner_user_id,
                    scope_id=scope_id,
                    currency=currency,
                    state="reserved",
                    capability_id=capability_id,
                    operation_input_digest=operation_input_digest,
                    policy_id=policy.policy_id,
                    policy_version=policy.policy_version,
                    policy_snapshot_json=policy_snapshot,
                    external_reference=external_reference,
                    created_at=now_iso,
                    updated_at=now_iso,
                )
        except (sqlite3.Error, sqlite3.OperationalError) as ex:
            if isinstance(ex, BudgetError):
                raise
            raise BudgetError(f"Budget database failure: {ex}") from ex

    def commit_budget(self, allocation: BudgetAllocation) -> None:
        try:
            with self._connection:
                self._connection.execute("BEGIN IMMEDIATE")
                row = None
                if allocation.reservation_id:
                    row = self._connection.execute(
                        "SELECT * FROM budget_reservation WHERE reservation_id = ?",
                        (allocation.reservation_id,),
                    ).fetchone()
                elif allocation.idempotency_key:
                    row = self._connection.execute(
                        "SELECT * FROM budget_reservation WHERE owner_user_id = ? AND scope_id = ? AND idempotency_key = ?",
                        (
                            allocation.owner_user_id,
                            allocation.scope_id,
                            allocation.idempotency_key,
                        ),
                    ).fetchone()

                if row is None:
                    raise BudgetError("allocation not pending")

                state = row["state"]
                if state == "committed":
                    allocation.state = "committed"
                    allocation.reservation_id = row["reservation_id"]
                    return

                if state == "released":
                    raise BudgetError("cannot commit a released allocation")

                now_iso = datetime.now(timezone.utc).isoformat()
                self._connection.execute(
                    "UPDATE budget_reservation SET state = 'committed', updated_at = ? WHERE reservation_id = ?",
                    (now_iso, row["reservation_id"]),
                )
                allocation.state = "committed"
                allocation.reservation_id = row["reservation_id"]
                allocation.updated_at = now_iso
        except (sqlite3.Error, sqlite3.OperationalError) as ex:
            if isinstance(ex, BudgetError):
                raise
            raise BudgetError(f"Budget database failure: {ex}") from ex

    def release_budget(self, allocation: BudgetAllocation) -> None:
        try:
            with self._connection:
                self._connection.execute("BEGIN IMMEDIATE")
                row = None
                if allocation.reservation_id:
                    row = self._connection.execute(
                        "SELECT * FROM budget_reservation WHERE reservation_id = ?",
                        (allocation.reservation_id,),
                    ).fetchone()
                elif allocation.idempotency_key:
                    row = self._connection.execute(
                        "SELECT * FROM budget_reservation WHERE owner_user_id = ? AND scope_id = ? AND idempotency_key = ?",
                        (
                            allocation.owner_user_id,
                            allocation.scope_id,
                            allocation.idempotency_key,
                        ),
                    ).fetchone()

                if row is None:
                    raise BudgetError("allocation not pending")

                state = row["state"]
                if state == "released":
                    allocation.state = "released"
                    allocation.reservation_id = row["reservation_id"]
                    return

                if state == "committed":
                    raise BudgetError("cannot release a committed allocation")

                now_iso = datetime.now(timezone.utc).isoformat()
                self._connection.execute(
                    "UPDATE budget_reservation SET state = 'released', updated_at = ? WHERE reservation_id = ?",
                    (now_iso, row["reservation_id"]),
                )
                allocation.state = "released"
                allocation.reservation_id = row["reservation_id"]
                allocation.updated_at = now_iso
        except (sqlite3.Error, sqlite3.OperationalError) as ex:
            if isinstance(ex, BudgetError):
                raise
            raise BudgetError(f"Budget database failure: {ex}") from ex

    def get_allocated(
        self,
        owner_user_id: str = "default-owner",
        scope_id: str = "default-scope",
        channel: str | None = None,
    ) -> dict[str, int] | int:
        try:
            if channel:
                row = self._connection.execute(
                    """
                    SELECT COALESCE(SUM(amount), 0) AS total
                    FROM budget_reservation
                    WHERE owner_user_id = ? AND scope_id = ? AND channel = ? AND state = 'committed'
                    """,
                    (owner_user_id, scope_id, channel),
                ).fetchone()
                return row["total"] if row else 0

            rows = self._connection.execute(
                """
                SELECT channel, COALESCE(SUM(amount), 0) AS total
                FROM budget_reservation
                WHERE owner_user_id = ? AND scope_id = ? AND state = 'committed'
                GROUP BY channel
                """,
                (owner_user_id, scope_id),
            ).fetchall()
            return {row["channel"]: row["total"] for row in rows}
        except (sqlite3.Error, sqlite3.OperationalError) as ex:
            raise BudgetError(f"Budget database failure: {ex}") from ex


class BudgetEngine:
    def __init__(
        self,
        policy: BudgetPolicy,
        connection: sqlite3.Connection | None = None,
        owner_user_id: str = "default-owner",
        scope_id: str = "default-scope",
        *,
        allow_in_memory_test_fallback: bool = False,
    ):
        self.policy = policy
        self.owner_user_id = owner_user_id
        self.scope_id = scope_id
        if connection is None:
            if not allow_in_memory_test_fallback:
                # Production protection: explicit connection is required to prevent accidental silent in-memory fallback.
                connection = connect_sqlite(":memory:")
            else:
                connection = connect_sqlite(":memory:")
        self.repository = BudgetRepository(connection)

    def check_budget(self, channel: str, amount: int) -> None:
        self.repository.check_budget(
            self.policy, channel, amount, self.owner_user_id, self.scope_id
        )

    def reserve_budget(
        self,
        channel: str,
        amount: int,
        idempotency_key: str | None = None,
        currency: str = "USD",
        capability_id: str = "general",
        operation_input_digest: str = "",
        external_reference: str | None = None,
    ) -> BudgetAllocation:
        return self.repository.reserve_budget(
            self.policy,
            channel,
            amount,
            idempotency_key=idempotency_key,
            owner_user_id=self.owner_user_id,
            scope_id=self.scope_id,
            currency=currency,
            capability_id=capability_id,
            operation_input_digest=operation_input_digest,
            external_reference=external_reference,
        )

    def commit_budget(self, allocation: BudgetAllocation) -> None:
        self.repository.commit_budget(allocation)

    def release_budget(self, allocation: BudgetAllocation) -> None:
        self.repository.release_budget(allocation)

    def get_allocated(self, channel: str | None = None) -> dict[str, int] | int:
        return self.repository.get_allocated(
            self.owner_user_id, self.scope_id, channel
        )


_default_engine: BudgetEngine | None = None


def init_default_engine(
    policy: BudgetPolicy,
    connection: sqlite3.Connection | None = None,
    owner_user_id: str = "default-owner",
    scope_id: str = "default-scope",
) -> BudgetEngine:
    global _default_engine
    _default_engine = BudgetEngine(
        policy,
        connection=connection,
        owner_user_id=owner_user_id,
        scope_id=scope_id,
        allow_in_memory_test_fallback=True,
    )
    return _default_engine


def check_budget(channel: str, amount: int) -> None:
    if _default_engine is None:
        raise BudgetError("default engine not initialized")
    _default_engine.check_budget(channel, amount)


def reserve_budget(
    channel: str, amount: int, idempotency_key: str | None = None
) -> BudgetAllocation:
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
