"""Compatibility entry point delegating to canonical upstream messaging gateway.

In canonical architecture, Telegram conversational ingress is managed by the upstream
Hermes messaging gateway (`gateway/run.py` and `plugins/platforms/telegram/**`).
This runner delegates execution directly to the upstream gateway lifecycle.
"""
from __future__ import annotations

import sys


def main() -> int:
    """Delegate directly to canonical upstream gateway runner."""
    from gateway.run import main as upstream_gateway_main

    try:
        res = upstream_gateway_main()
        return 0 if res is None or res is True else int(res)
    except (KeyboardInterrupt, SystemExit) as exc:
        code = getattr(exc, "code", 0)
        return int(code) if code is not None and isinstance(code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
