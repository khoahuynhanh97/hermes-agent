from __future__ import annotations

from hermes_personal.gateway.plugin import register as register_gateway
from hermes_personal.runtime.plugin import register as register_start


def register(ctx) -> None:
    register_gateway(ctx)
    register_start(ctx)
