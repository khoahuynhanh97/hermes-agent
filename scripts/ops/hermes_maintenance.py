from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hermes.adapters.local.windows_runtime_processes import (  # noqa: E402
    WindowsHermesProcessController,
)
from hermes.backup import SQLiteBackupManager  # noqa: E402
from hermes.data_health import AuditReport, DataHealth  # noqa: E402
from hermes.db import Database  # noqa: E402
from hermes.maintenance import MaintenanceRunner  # noqa: E402
from hermes.config import get_data_root  # noqa: E402


EXIT_CONFIRMATION_REQUIRED = 2
EXIT_SQLITE_REQUIRED = 3
EXIT_RUN_FAILED = 4
EXIT_MANUAL_INTERVENTION = 5
EXIT_COMMAND_ERROR = 6


@dataclass(frozen=True)
class CommandResult:
    status: str
    report_json: str
    report_markdown: str


@dataclass(frozen=True)
class _ProductionPaths:
    data_dir: Path
    database: Path
    backups: Path
    reports: Path


def _resolve_paths(environ: Mapping[str, str]) -> _ProductionPaths:
    configured_data = environ.get("HERMES_DATA_DIR", "").strip()
    if configured_data:
        data_dir = Path(configured_data).expanduser().resolve()
    else:
        data_dir = get_data_root()
    database_value = environ.get("HERMES_DB_PATH", "").strip()
    backup_value = environ.get("HERMES_BACKUP_DIR", "").strip()
    report_value = environ.get(
        "HERMES_MAINTENANCE_REPORT_DIR",
        "",
    ).strip()
    return _ProductionPaths(
        data_dir=data_dir,
        database=(
            Path(database_value).expanduser().resolve()
            if database_value
            else data_dir / "db" / "hermes.db"
        ),
        backups=(
            Path(backup_value).expanduser().resolve()
            if backup_value
            else data_dir / "backups"
        ),
        reports=(
            Path(report_value).expanduser().resolve()
            if report_value
            else data_dir / "maintenance_reports"
        ),
    )


def _build_runner(environ: Mapping[str, str]) -> MaintenanceRunner:
    paths = _resolve_paths(environ)
    database = Database(paths.database)
    return MaintenanceRunner(
        process_controller=WindowsHermesProcessController(repo_root=ROOT),
        backup_manager=SQLiteBackupManager(
            database=database,
            backup_dir=paths.backups,
        ),
        data_health=DataHealth(database),
        report_dir=paths.reports,
    )


def _audit_payload(report: AuditReport) -> dict[str, object]:
    severity = Counter(finding.severity for finding in report.findings)
    repair_class = Counter(
        finding.repair_class for finding in report.findings
    )
    return {
        "status": "audit_completed",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "integrity_ok": report.integrity == "ok",
        "foreign_keys_ok": report.foreign_key_violations == 0,
        "schema_version": report.schema_version,
        "counts": {
            key: int(value)
            for key, value in sorted(report.counts.items())
        },
        "finding_count": len(report.findings),
        "severity_counts": {
            key: severity[key] for key in ("info", "warning", "error")
        },
        "repair_class_counts": {
            key: repair_class[key]
            for key in ("safe", "review", "forbidden")
        },
        "planned_action_count": len(report.repair_plan.actions),
    }


def _reserve_audit_paths(report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    for _attempt in range(10):
        token = uuid.uuid4().hex
        stem = f"audit-{token}"
        json_path = report_dir / f"{stem}.json"
        markdown_path = report_dir / f"{stem}.md"
        json_reserved = False
        try:
            with json_path.open("x", encoding="utf-8"):
                pass
            json_reserved = True
            with markdown_path.open("x", encoding="utf-8"):
                pass
            return json_path, markdown_path
        except FileExistsError:
            if json_reserved:
                json_path.unlink()
    raise RuntimeError("could not reserve audit report paths")


def _run_audit(environ: Mapping[str, str]) -> CommandResult:
    paths = _resolve_paths(environ)
    report = DataHealth(Database(paths.database)).audit()
    payload = _audit_payload(report)
    json_path, markdown_path = _reserve_audit_paths(paths.reports)
    json_text = (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        + "\n"
    )
    markdown_text = (
        "# Hermes Read-Only Audit\n\n"
        "```json\n"
        + json_text
        + "```\n"
    )
    json_path.write_text(json_text, encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    return CommandResult(
        status="audit_completed",
        report_json=str(json_path),
        report_markdown=str(markdown_path),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit or maintain the production Hermes SQLite store."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--confirm-live", action="store_true")
    return parser


def _emit(stdout: TextIO, result: CommandResult) -> None:
    print(
        json.dumps(
            {
                "report_json": result.report_json,
                "report_markdown": result.report_markdown,
                "status": result.status,
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
        file=stdout,
    )


def _emit_status(stdout: TextIO, status: str) -> None:
    print(
        json.dumps({"status": status}, sort_keys=True),
        file=stdout,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
) -> int:
    arguments = _parser().parse_args(argv)
    active_environ = environ if environ is not None else os.environ
    output = stdout or sys.stdout

    if arguments.command == "audit":
        try:
            result = _run_audit(active_environ)
        except Exception:
            _emit_status(output, "failed")
            return EXIT_COMMAND_ERROR
        _emit(output, result)
        return 0

    if not arguments.confirm_live:
        _emit_status(output, "refused")
        return EXIT_CONFIRMATION_REQUIRED
    backend = active_environ.get(
        "HERMES_STORAGE_BACKEND",
        "sqlite",
    ).strip().casefold()
    if backend != "sqlite":
        _emit_status(output, "refused")
        return EXIT_SQLITE_REQUIRED

    try:
        result = _build_runner(active_environ).run()
    except Exception:
        _emit_status(output, "failed")
        return EXIT_COMMAND_ERROR
    command_result = CommandResult(
        status=result.status,
        report_json=result.report_json,
        report_markdown=result.report_markdown,
    )
    _emit(output, command_result)
    if result.status == "completed":
        return 0
    if result.status == "manual_intervention_required":
        return EXIT_MANUAL_INTERVENTION
    return EXIT_RUN_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
