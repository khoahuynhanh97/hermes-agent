"""hermes_personal/api

Backward compatibility shim package.

The application server functionality has been consolidated into
hermes_personal.application. This module re-exports from application.server
for backward compatibility.

New code should use hermes_personal.application.server directly.
"""
from __future__ import annotations

from hermes_personal.application.server import (
    compute_static_bundle_digest,
    verify_static_bundle_digest,
    create_proxy_application,
    create_application,
    main,
)

__all__ = [
    "compute_static_bundle_digest",
    "verify_static_bundle_digest",
    "create_proxy_application", 
    "create_application",
    "main",
]
