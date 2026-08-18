import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Iterator

current_principal: contextvars.ContextVar[Optional["PrincipalContext"]] = contextvars.ContextVar(
    "current_principal", default=None
)


@dataclass(frozen=True)
class PrincipalContext:
    actor_id: str
    owner_user_id: str
    platform: str
    session_id: str
    roles: Tuple[str, ...] = ()


def set_current_principal(principal: Optional[PrincipalContext]) -> contextvars.Token:
    return current_principal.set(principal)


def bind_principal_arguments(
    args: Dict[str, Any],
    principal: Optional[PrincipalContext],
    principal_mode: str = "session",
) -> Dict[str, Any]:
    bound = dict(args)
    if principal_mode == "session":
        if principal is None:
            raise PermissionError("Principal context is required for session-scoped tool dispatch")
        bound["owner_user_id"] = principal.owner_user_id
    return bound


@contextmanager
def principal_scope(principal: PrincipalContext) -> Iterator[PrincipalContext]:
    """Bind ``principal`` for the duration of the current turn.

    Rejects attempts by a nested channel to replace an existing principal
    with a different actor/owner. The outer scope wins — a nested agent
    turn cannot impersonate the outer caller.

    Uses contextvars so the binding survives across asyncio.create_task
    boundaries that copy the current context, but does not leak across
    threads unless the caller explicitly copies the Context.
    """
    existing = current_principal.get()
    if existing is not None:
        if (
            existing.actor_id != principal.actor_id
            or existing.owner_user_id != principal.owner_user_id
            or existing.platform != principal.platform
            or existing.session_id != principal.session_id
        ):
            yield existing
            return
        yield existing
        return
    token = current_principal.set(principal)
    try:
        yield principal
    finally:
        current_principal.reset(token)