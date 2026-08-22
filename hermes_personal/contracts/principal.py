from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChannelName = Literal["telegram", "cli", "web", "omni"]


@dataclass(frozen=True)
class PrincipalContext:
    actor_id: str
    owner_user_id: str
    channel: ChannelName
    session_id: str
    roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.channel not in {"telegram", "cli", "web", "omni"}:
            raise ValueError(f"unsupported channel: {self.channel}")
        for field_name in ("actor_id", "owner_user_id", "session_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be blank")
