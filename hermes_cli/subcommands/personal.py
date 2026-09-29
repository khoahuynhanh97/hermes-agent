"""``hermes personal`` subcommand parser for Hermes Personal workflows.

Provides CLI integration for daily product video selection, automation,
and operator approval gates.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from hermes_personal.product_video.automation.importer import DEFAULT_EXCHANGE_INBOX
from hermes_personal.product_video.cli import (

    cmd_approve,
    cmd_list,
    cmd_select,
    cmd_start,
    cmd_status,
    cmd_daily_status,
    cmd_recover_keyframe,
)


def _default_personal_action(parser: argparse.ArgumentParser) -> Callable:
    def _action(args: argparse.Namespace) -> int:
        parser.print_help()
        return 0
    return _action


def build_personal_parser(subparsers, *, cmd_personal: Callable | None = None) -> None:
    """Attach the ``personal`` subcommand to `subparsers`."""
    personal_parser = subparsers.add_parser(
        "personal",
        help="Hermes Personal workflows, product video factory, and operator gates",
        description=(
            "Hermes Personal bounded context commands for daily product scouting, "
            "video production automation, and operator approvals."
        ),
    )
    personal_subs = personal_parser.add_subparsers(dest="personal_subcommand", metavar="<domain>")

    # hermes personal video ...
    video_parser = personal_subs.add_parser(
        "video",
        aliases=["pv", "product-video"],
        help="Manage daily product video selection, automation, and approvals",
        description="Daily Product Selection and Video Production Factory.",
    )
    video_parser.add_argument("--db-path", default=None, help="Path to SQLite database file")
    video_parser.add_argument(
        "--inbox-root",
        type=Path,
        default=DEFAULT_EXCHANGE_INBOX,
        help="Path to exchange inbox containing READY batches",
    )
    video_parser.add_argument(
        "--legacy-source-root",
        dest="legacy_source_root",
        type=Path,
        default=None,
        help="[MIGRATION/DEBUG ONLY] Path to raw daily_runs directory. Never used in production.",
    )

    video_subs = video_parser.add_subparsers(dest="video_subcommand", metavar="<command>")


    p_list = video_subs.add_parser("list", aliases=["ls"], help="List scouted products and their video production status")
    p_list.add_argument("--date", default=None, help="Scan date (YYYY-MM-DDi, default latest")
    p_list.add_argument(
        "--status",
        choices=["all", "unprocessed", "awaiting_product_lock", "in_production", "completed", "invalid"],
        default="all",
        help="Filter products by UI status",
    )
    p_list.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_list.set_defaults(func=cmd_list)


    p_start = video_subs.add_parser("start", help="Start video production workflows for products")
    p_start.add_argument("--auto", action="store_true", help="Automatically select eligible unprocessed products")
    p_start.add_argument("--limit", type=int, default=5, help="Max products to start in auto mode (default: 5)")
    p_start.add_argument("product_keys", nargs="*", help="Specific product key(s) to start")
    p_start.add_argument("--product-keys", dest="flag_product_keys", nargs="+", help="Specific product keys (flag format)")
    p_start.add_argument("--date", default=None, help="Scan date (YYYY-MM-DD or today)")
    p_start.add_argument("--minimum-daily", type=int, default=0, help="Return an error when fewer workflows start on this date")
    p_start.add_argument("--owner-user-id", default="local-owner", help="Owner ID for workflow audit")
    p_start.add_argument("--provider-mode", default="configured", choices=["configured", "fake"])
    p_start.add_argument(
        "--no-research",
        dest="with_research",
        action="store_false",
        help="Do not run MCP research worker after workflow creation",
    )
    p_start.set_defaults(with_research=True, func=_wrap_start_cmd)


    p_select = video_subs.add_parser("select", help="Interactive terminal menu to choose products for video creation")
    p_select.add_argument("--date", default=None, help="Scan date (YYYY-MM-DD)")
    p_select.add_argument("--owner-user-id", default="local-owner")
    p_select.add_argument("--provider-mode", default="configured", choices=["configured", "fake"])
    p_select.add_argument("--no-research", dest="with_research", action="store_false")
    p_select.set_defaults(with_research=True, func=cmd_select)


    p_approve = video_subs.add_parser(
        "approve",
        aliases=["approve-lock"],
        help="Approve Product Lock (or other gate) to advance the workflow",
    )
    p_approve.add_argument("target_id", help="Approval Request ID (UUID) or Workflow ID (e.g. pv-daily-...)")
    p_approve.add_argument("--owner-user-id", default="local-owner")
    p_approve.add_argument("--authorize-cost", action="store_true", help="Authorize positive cost for paid video render")
    p_approve.add_argument("--provider-mode", default="configured", choices=["configured", "fake"], help="Provider mode for worker loop")
    p_approve.set_defaults(func=cmd_approve)


    p_status = video_subs.add_parser("status", help="Inspect detailed status of a specific workflow")
    p_status.add_argument("workflow_id", help="Workflow ID (e.g. pv-daily-1e96ac740ec2f41f)")
    p_status.set_defaults(func=cmd_status)

    p_daily_status = video_subs.add_parser("daily-status", help="Report completed product videos for a PI batch date")
    p_daily_status.add_argument("--date", default="today", help="PI batch date (YYYY-MM-DD or today)")
    p_daily_status.add_argument("--minimum", type=int, default=3, help="Minimum completed exports for success")
    p_daily_status.add_argument("--json", action="store_true")
    p_daily_status.set_defaults(func=cmd_daily_status)

    p_recover = video_subs.add_parser(
        "recover-keyframe", help="Reconcile an unknown keyframe and authorize only its missing replacement"
    )
    p_recover.add_argument("workflow_id")
    p_recover.add_argument("--owner-user-id", default="local-owner")
    p_recover.add_argument("--authorization-run-id", default=None)
    p_recover.add_argument("--authorization-scope", action="append", default=[])
    p_recover.add_argument("--authorization-expires-at", default=None)
    p_recover.add_argument("--authorization-max-cost-usd", type=float, default=None)
    p_recover.add_argument("--authorization-campaign-id", default=None)
    p_recover.set_defaults(func=cmd_recover_keyframe)


    video_parser.set_defaults(func=_default_personal_action(video_parser))
    personal_parser.set_defaults(func=cmd_personal or _default_personal_action(personal_parser))


def _wrap_start_cmd(args: argparse.Namespace) -> int:
    keys: list[str] = []
    if getattr(args, "product_keys", None):
        keys.extend(args.product_keys)
    if getattr(args, "flag_product_keys", None):
        keys.extend(args.flag_product_keys)
    args.product_keys = keys
    return cmd_start(args)
