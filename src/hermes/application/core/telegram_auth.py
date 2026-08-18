"""Small Telegram authorization helper for the personal Hermes bot."""

from __future__ import annotations

import os

from hermes.runtime import config


def parse_user_ids(value: str | None) -> set[int]:
    """Parse comma/space/semicolon separated Telegram numeric IDs."""
    allowed: set[int] = set()
    for token in (value or "").replace(";", ",").replace(" ", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            allowed.add(int(token))
        except ValueError:
            continue
    return allowed


def get_allowed_user_ids() -> set[int]:
    """Return the configured allowlist, failing closed when it is absent."""
    configured = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    if not configured:
        configured = getattr(config, "TELEGRAM_ALLOWED_USER_IDS", "")

    allowed = parse_user_ids(configured)
    if allowed:
        return allowed

    # Backward-compatible single-owner fallback for the existing private bot.
    # New deployments should set TELEGRAM_ALLOWED_USER_IDS explicitly.
    return parse_user_ids(getattr(config, "TELEGRAM_REVIEW_CHAT_ID", ""))


def is_authorized_user_id(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return int(user_id) in get_allowed_user_ids()


def is_authorized_update(update) -> bool:
    user = getattr(update, "effective_user", None)
    return is_authorized_user_id(getattr(user, "id", None))
