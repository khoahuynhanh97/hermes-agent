from __future__ import annotations

from typing import TYPE_CHECKING

from hermes_personal.runtime.cli import handle_start, setup_start_parser

if TYPE_CHECKING:
    from hermes_cli.plugins import PluginContext


def register(ctx: PluginContext) -> None:
    """Register the exact 'hermes start' command through the public PluginContext API."""
    if hasattr(ctx, "register_cli_command"):
        ctx.register_cli_command(
            name="start",
            help="Start the complete Hermes personal runtime",
            description="Validate, recover, start, and supervise every Hermes service.",
            setup_fn=setup_start_parser,
            handler_fn=handle_start,
        )
