from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence


@dataclass(frozen=True)
class LifecycleActor:
    actor_id: str
    role: Literal["owner", "system"] = "owner"

    @classmethod
    def owner(cls, actor_id: str | int) -> "LifecycleActor":
        return cls(str(actor_id), "owner")

    @classmethod
    def system(cls, name: str) -> "LifecycleActor":
        return cls(name, "system")


@dataclass(frozen=True)
class LifecycleCommand:
    action: Literal["approve", "reject", "request_reanalysis"]
    lesson_id: str
    actor: LifecycleActor
    mode: str = ""
    reason: str = ""
    expected_status: str | None = None
    force: bool = False


@dataclass(frozen=True)
class LifecycleResult:
    ok: bool
    code: str
    changed: bool
    lesson: dict | None = None


class _LifecycleStore(Protocol):
    def apply_lifecycle_commands(
        self, commands: Sequence[LifecycleCommand]
    ) -> list[LifecycleResult]: ...


class KnowledgeLifecycle:
    def __init__(self, store: _LifecycleStore):
        self.store = store

    def approve(
        self,
        lesson_id: str,
        actor: LifecycleActor,
        mode: str = "",
        *,
        force: bool = False,
    ) -> LifecycleResult:
        return self.apply(
            [
                LifecycleCommand(
                    "approve",
                    lesson_id,
                    actor,
                    mode=mode,
                    force=force,
                )
            ]
        )[0]

    def reject(
        self,
        lesson_id: str,
        actor: LifecycleActor,
        reason: str = "",
    ) -> LifecycleResult:
        return self.apply(
            [LifecycleCommand("reject", lesson_id, actor, reason=reason)]
        )[0]

    def request_reanalysis(
        self,
        lesson_id: str,
        actor: LifecycleActor,
    ) -> LifecycleResult:
        return self.apply(
            [LifecycleCommand("request_reanalysis", lesson_id, actor)]
        )[0]

    def apply(
        self, commands: Sequence[LifecycleCommand]
    ) -> list[LifecycleResult]:
        return self.store.apply_lifecycle_commands(commands)
