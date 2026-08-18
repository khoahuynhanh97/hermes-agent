"""Channel ingress for PrincipalContext.

Channel adapters authenticate the request, build a PrincipalContext
from the authenticated identity, and bind it via principal_scope() so
downstream dispatch enforces the owner/actor for every tool call.

AIAgent.run_conversation() must consume the bound principal via the
ContextVar — never invent a new owner from arguments.
"""

from contextlib import contextmanager
from typing import Iterator, Optional

from hermes.security.principal import (
    PrincipalContext,
    current_principal,
)


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


def build_local_cli_principal(
    session_id: str = "cli_session",
    *,
    owner_id: Optional[str] = None,
    admin: Optional[bool] = None,
) -> PrincipalContext:
    """Build a local principal from CLI environment.

    Identity comes from HERMES_CLI_USER_ID, then OS user. Admin role
    is granted only when HERMES_LOCAL_ADMIN=true is explicit.
    """
    import getpass
    import os

    resolved_owner = (
        owner_id
        or os.environ.get("HERMES_CLI_USER_ID")
        or getpass.getuser()
    )
    is_admin = (
        admin
        if admin is not None
        else os.environ.get("HERMES_LOCAL_ADMIN", "false").lower() == "true"
    )
    return PrincipalContext(
        actor_id=resolved_owner,
        owner_user_id=resolved_owner,
        platform="cli",
        session_id=session_id,
        roles=("admin",) if is_admin else (),
    )


def build_local_oneshot_principal(session_id: str = "oneshot_session") -> PrincipalContext:
    """Build a local principal for oneshot (-z) mode."""
    import getpass
    import os

    resolved_owner = os.environ.get("HERMES_CLI_USER_ID") or getpass.getuser()
    is_admin = os.environ.get("HERMES_LOCAL_ADMIN", "false").lower() == "true"
    return PrincipalContext(
        actor_id=resolved_owner,
        owner_user_id=resolved_owner,
        platform="oneshot",
        session_id=session_id,
        roles=("admin",) if is_admin else (),
    )


def build_gui_principal(session_id: str = "gui_session") -> PrincipalContext:
    """Build a local principal for the GUI Assistant tab.

    Identity comes from HERMES_GUI_OWNER_USER_ID, then OS user.
    Admin role is granted only when HERMES_LOCAL_ADMIN=true is explicit.
    """
    import getpass
    import os

    resolved_owner = (
        os.environ.get("HERMES_GUI_OWNER_USER_ID")
        or os.environ.get("HERMES_CLI_USER_ID")
        or getpass.getuser()
    )
    is_admin = os.environ.get("HERMES_LOCAL_ADMIN", "false").lower() == "true"
    return PrincipalContext(
        actor_id=resolved_owner,
        owner_user_id=resolved_owner,
        platform="gui",
        session_id=session_id,
        roles=("admin",) if is_admin else (),
    )


def build_gateway_principal(
    *,
    actor_id: str,
    owner_user_id: str,
    platform: str,
    session_id: str = "gateway_session",
    roles: tuple = (),
) -> PrincipalContext:
    """Build a principal for gateway user-originated turns."""
    return PrincipalContext(
        actor_id=actor_id,
        owner_user_id=owner_user_id,
        platform=platform,
        session_id=session_id,
        roles=roles,
    )


def build_api_principal(session_id: str = "api_session") -> Optional[PrincipalContext]:
    """Build a principal for the OpenAI-compatible API server.

    Returns None when HERMES_API_OWNER_USER_ID is unset — the API
    server must reject unauthenticated requests with 401.
    """
    import os

    resolved_owner = os.environ.get("HERMES_API_OWNER_USER_ID", "").strip()
    if not resolved_owner:
        return None
    return PrincipalContext(
        actor_id=resolved_owner,
        owner_user_id=resolved_owner,
        platform="api_server",
        session_id=session_id,
        roles=("admin",),
    )