"""Compatibility shim for hermes_personal.integrations.video_factory.server.

DEPRECATED / DECLARED_ONLY: This module is a thin re-export compatibility shim.
Production ownership lives in hermes_personal.integrations.video_factory.server.
"""
from __future__ import annotations

from hermes_personal.integrations.video_factory.server import *
from hermes_personal.integrations.video_factory.server import mcp

if __name__ == "__main__":
    from hermes_personal.integrations.video_factory import main
    main()
