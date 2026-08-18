from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .application.knowledge_lifecycle import LifecycleActor, LifecycleCommand
from .db import SCHEMA_VERSION, Database
from .knowledge import SQLiteKnowledgeStore, build_lesson_fts_values


Severity = Literal["info", "warning", "error"]
RepairClass = Literal["safe", "review", "forbidden"]
RepairKind = Literal["rebuild_fts", "set_approved_at", "reject_lesson"]
Metadata = dict[str, int | str | bool]
ActionStatus = Literal["applied", "skipped"]

COUNT_KEYS = (
    "lessons",
    "pending",
    "approved",
    "rejected",
    "sources",
    "evidence",
    "lesson_events",
    "fts_rows",
)
REQUIRED_TABLES = {
    "evidence",
    "lesson_evidence",
    "lesson_events",
    "lesson_fts",
    "lessons",
    "sources",
}
DEFECT_MARKERS = {
    "needs_reanalysis",
    "unknown_title",
    "error_category",
}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    subject_type: str
    subject_id_hash: str
    repair_class: RepairClass
    metadata: Metadata


@dataclass(frozen=True)
class RepairAction:
    action_id: str
    kind: RepairKind
    subject_id: str
    expected: Metadata


@dataclass(frozen=True)
class RepairPlan:
    actions: tuple[RepairAction, ...] = ()


@dataclass(frozen=True)
class AuditReport:
    integrity: str
    foreign_key_violations: int
    schema_version: int
    counts: dict[str, int]
    findings: tuple[Finding, ...]
    repair_plan: RepairPlan


@dataclass(frozen=True)
class ActionOutcome:
    action_id: str
    kind: RepairKind
    status: ActionStatus
    reason: Literal["applied", "already_applied", "precondition_failed"]
    before: Metadata
    after: Metadata


@dataclass(frozen=True)
class RepairReport:
    planned_count: int
    applied_count: int
    skipped_count: int
    applied_action_ids: tuple[str, ...]
    skipped_action_ids: tuple[str, ...]
    outcomes: tuple[ActionOutcome, ...]


@dataclass(frozen=True)
class _FtsDrift:
    code: Literal["fts_missing", "fts_mismatch", "fts_orphan", "fts_extra"]
    subject_id: str
    row_count: int
    actual_hash: str
    expected_hash: str


class _RepairPostconditionFailed(RuntimeError):
    pass


def _subject_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalized(value: str | None) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().casefold()


def _is_unknown_title(value: str | None) -> bool:
    target = _normalized("Không xác định")
    raw = value or ""
    if _normalized(raw) == target:
        return True
    for encoding in ("cp1252", "latin1"):
        try:
            repaired = raw.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if _normalized(repaired) == target:
            return True
    return False


def _empty_counts() -> dict[str, int]:
    return {key: 0 for key in COUNT_KEYS}


def _valid_timestamp(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text or ("T" not in text and " " not in text):
        return False
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _action(
    kind: RepairKind,
    subject_id_hash: str,
    expected: Metadata,
) -> RepairAction:
    canonical = json.dumps(
        {
            "kind": kind,
            "subject_id": subject_id_hash,
            "expected": expected,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return RepairAction(
        action_id=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        kind=kind,
        subject_id=subject_id_hash,
        expected=expected,
    )


class DataHealth:
    """Read-only knowledge audit and deterministic transactional repair."""

    def __init__(
        self,
        database: Database,
        *,
        legacy_index_path: str | Path | None = None,
        store: SQLiteKnowledgeStore | None = None,
    ):
        self.database = database
        self.legacy_index_path = (
            Path(legacy_index_path).expanduser().resolve()
            if legacy_index_path is not None
            else None
        )
        self.store = store or SQLiteKnowledgeStore(
            database,
            initialize_database=False,
        )

    def _read_only_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.database.path.as_posix()}?mode=ro",
            uri=True,
            timeout=self.database.busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.database.busy_timeout_ms}")
        return connection

    @staticmethod
    def _expected_fts(row: sqlite3.Row) -> tuple[str, ...]:
        return build_lesson_fts_values(row)

    @classmethod
    def _fts_drift(
        cls,
        connection: sqlite3.Connection,
    ) -> tuple[list[_FtsDrift], str]:
        lesson_rows = connection.execute(
            """
            SELECT id, owner_user_id, title, summary, content, tags_json,
                   key_lessons_json, status
            FROM lessons ORDER BY id
            """
        ).fetchall()
        lessons = {str(row["id"]): row for row in lesson_rows}
        actual_rows = connection.execute(
            """
            SELECT rowid, lesson_id, owner_user_id, title, summary, content, tags
            FROM lesson_fts ORDER BY lesson_id, rowid
            """
        ).fetchall()
        actual_by_id: dict[str, list[tuple[str, ...]]] = {}
        for row in actual_rows:
            lesson_id = str(row["lesson_id"])
            actual_by_id.setdefault(lesson_id, []).append(
                tuple(str(row[key] or "") for key in row.keys()[1:])
            )

        drift: list[_FtsDrift] = []
        approved_ids = {
            lesson_id
            for lesson_id, row in lessons.items()
            if row["status"] == "approved"
        }
        for lesson_id in sorted(approved_ids):
            actual = actual_by_id.get(lesson_id, [])
            expected = cls._expected_fts(lessons[lesson_id])
            expected_hash = _subject_hash(
                json.dumps(expected, ensure_ascii=False)
            )
            if not actual:
                drift.append(
                    _FtsDrift(
                        "fts_missing",
                        lesson_id,
                        0,
                        "",
                        expected_hash,
                    )
                )
            elif len(actual) != 1 or actual[0] != expected:
                drift.append(
                    _FtsDrift(
                        "fts_mismatch",
                        lesson_id,
                        len(actual),
                        _subject_hash(
                            json.dumps(actual, ensure_ascii=False)
                        ),
                        expected_hash,
                    )
                )

        for lesson_id in sorted(actual_by_id):
            actual = actual_by_id[lesson_id]
            actual_hash = _subject_hash(
                json.dumps(actual, ensure_ascii=False)
            )
            if lesson_id not in lessons:
                drift.append(
                    _FtsDrift(
                        "fts_orphan",
                        lesson_id,
                        len(actual),
                        actual_hash,
                        "",
                    )
                )
            elif lesson_id not in approved_ids:
                drift.append(
                    _FtsDrift(
                        "fts_extra",
                        lesson_id,
                        len(actual),
                        actual_hash,
                        "",
                    )
                )

        drift_preconditions = [
            (
                item.code,
                _subject_hash(item.subject_id),
                item.row_count,
                item.actual_hash,
                item.expected_hash,
            )
            for item in drift
        ]
        fingerprint = hashlib.sha256(
            json.dumps(
                drift_preconditions,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return drift, fingerprint

    @staticmethod
    def _finding(
        code: str,
        severity: Severity,
        subject_type: str,
        subject_id: str,
        repair_class: RepairClass,
        metadata: Metadata | None = None,
    ) -> Finding:
        return Finding(
            code=code,
            severity=severity,
            subject_type=subject_type,
            subject_id_hash=_subject_hash(subject_id),
            repair_class=repair_class,
            metadata=metadata or {},
        )

    def _legacy_findings(self, sqlite_count: int) -> list[Finding]:
        if self.legacy_index_path is None:
            return []
        try:
            payload = json.loads(
                self.legacy_index_path.read_text(encoding="utf-8-sig")
            )
            entries = payload.get("entries", []) if isinstance(payload, dict) else payload
            if not isinstance(entries, list):
                raise ValueError("legacy index has no entries list")
        except (OSError, json.JSONDecodeError, ValueError):
            return [
                self._finding(
                    "legacy_index_unreadable",
                    "warning",
                    "legacy_index",
                    str(self.legacy_index_path),
                    "review",
                    {"readable": False},
                )
            ]
        if len(entries) == sqlite_count:
            return []
        return [
            self._finding(
                "legacy_count_drift",
                "warning",
                "legacy_index",
                str(self.legacy_index_path),
                "review",
                {"legacy_count": len(entries), "sqlite_count": sqlite_count},
            )
        ]

    def _forbidden_audit(
        self,
        code: str,
        *,
        integrity: str = "unavailable",
        foreign_key_violations: int = 0,
        schema_version: int = 0,
        metadata: Metadata | None = None,
    ) -> AuditReport:
        return AuditReport(
            integrity=integrity,
            foreign_key_violations=foreign_key_violations,
            schema_version=schema_version,
            counts=_empty_counts(),
            findings=(
                self._finding(
                    code,
                    "error",
                    "database",
                    str(self.database.path),
                    "forbidden",
                    metadata,
                ),
            ),
            repair_plan=RepairPlan(),
        )

    def audit(self) -> AuditReport:
        if not self.database.path.is_file():
            return self._forbidden_audit(
                "database_missing",
                metadata={"exists": False},
            )

        findings: list[Finding] = []
        timestamp_actions: list[RepairAction] = []
        rejection_actions: list[RepairAction] = []
        rebuild_actions: list[RepairAction] = []

        try:
            connection = self._read_only_connection()
        except sqlite3.Error:
            return self._forbidden_audit(
                "database_unreadable",
                metadata={"readable": False},
            )
        try:
            integrity_rows = connection.execute(
                "PRAGMA integrity_check"
            ).fetchall()
            integrity_messages = [str(row[0]) for row in integrity_rows]
            integrity = (
                "ok"
                if integrity_messages == ["ok"]
                else f"failed:{len(integrity_messages)}"
            )
            if integrity != "ok":
                findings.append(
                    self._finding(
                        "integrity_check_failed",
                        "error",
                        "database",
                        str(self.database.path),
                        "forbidden",
                        {"issue_count": len(integrity_messages)},
                    )
                )

            foreign_key_violations = 0
            schema_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
            table_names = {
                str(row["name"])
                for row in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table'
                    """
                ).fetchall()
            }
            missing_tables = REQUIRED_TABLES - table_names
            if missing_tables or schema_version != SCHEMA_VERSION:
                findings.append(
                    self._finding(
                        "schema_incompatible",
                        "error",
                        "database",
                        str(self.database.path),
                        "forbidden",
                        {
                            "missing_table_count": len(missing_tables),
                            "schema_version_matches": (
                                schema_version == SCHEMA_VERSION
                            ),
                        },
                    )
                )
                findings.sort(key=lambda item: item.code)
                return AuditReport(
                    integrity=integrity,
                    foreign_key_violations=foreign_key_violations,
                    schema_version=schema_version,
                    counts=_empty_counts(),
                    findings=tuple(findings),
                    repair_plan=RepairPlan(),
                )

            foreign_key_rows = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            foreign_key_violations = len(foreign_key_rows)
            if foreign_key_violations:
                findings.append(
                    self._finding(
                        "foreign_key_violation",
                        "error",
                        "database",
                        str(self.database.path),
                        "forbidden",
                        {"violation_count": foreign_key_violations},
                    )
                )

            counts = {
                "lessons": int(
                    connection.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
                ),
                "pending": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM lessons WHERE status = 'pending'"
                    ).fetchone()[0]
                ),
                "approved": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM lessons WHERE status = 'approved'"
                    ).fetchone()[0]
                ),
                "rejected": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM lessons WHERE status = 'rejected'"
                    ).fetchone()[0]
                ),
                "sources": int(
                    connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
                ),
                "evidence": int(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
                ),
                "lesson_events": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM lesson_events"
                    ).fetchone()[0]
                ),
                "fts_rows": int(
                    connection.execute("SELECT COUNT(*) FROM lesson_fts").fetchone()[0]
                ),
            }

            drift, drift_hash = self._fts_drift(connection)
            for item in drift:
                findings.append(
                    self._finding(
                        item.code,
                        "error",
                        "lesson_fts",
                        item.subject_id,
                        "safe",
                        {"row_count": item.row_count},
                    )
                )
            if drift:
                rebuild_actions.append(
                    _action(
                        "rebuild_fts",
                        _subject_hash("lesson_fts"),
                        {
                            "drift_hash": drift_hash,
                            "finding_count": len(drift),
                        },
                    )
                )

            lesson_rows = connection.execute(
                """
                SELECT id, status, needs_reanalysis, title, category, approved_at
                FROM lessons ORDER BY id
                """
            ).fetchall()
            for row in lesson_rows:
                lesson_id = str(row["id"])
                status = str(row["status"])
                defect_expected: Metadata = {"status": status}
                if bool(row["needs_reanalysis"]):
                    findings.append(
                        self._finding(
                            "defect_needs_reanalysis",
                            "error",
                            "lesson",
                            lesson_id,
                            "safe",
                            {"status_approved": status == "approved"},
                        )
                    )
                    defect_expected["needs_reanalysis"] = True
                if _is_unknown_title(row["title"]):
                    findings.append(
                        self._finding(
                            "defect_unknown_title",
                            "error",
                            "lesson",
                            lesson_id,
                            "safe",
                            {"status_approved": status == "approved"},
                        )
                    )
                    defect_expected["unknown_title"] = True
                if _normalized(row["category"]) == "error":
                    findings.append(
                        self._finding(
                            "defect_error_category",
                            "error",
                            "lesson",
                            lesson_id,
                            "safe",
                            {"status_approved": status == "approved"},
                        )
                    )
                    defect_expected["error_category"] = True
                has_deterministic_defect = len(defect_expected) > 1
                if has_deterministic_defect and status != "rejected":
                    rejection_actions.append(
                        _action(
                            "reject_lesson",
                            _subject_hash(lesson_id),
                            defect_expected,
                        )
                    )

                if status == "approved" and row["approved_at"] is None:
                    approved_events = connection.execute(
                        """
                        SELECT created_at FROM lesson_events
                        WHERE lesson_id = ? AND action = 'approved'
                        ORDER BY id
                        """,
                        (lesson_id,),
                    ).fetchall()
                    if len(approved_events) == 1:
                        event_created_at = str(approved_events[0]["created_at"])
                        if _valid_timestamp(event_created_at):
                            findings.append(
                                self._finding(
                                    "approved_at_missing_unambiguous",
                                    "error",
                                    "lesson",
                                    lesson_id,
                                    "safe",
                                    {"approved_event_count": 1},
                                )
                            )
                            if not has_deterministic_defect:
                                timestamp_actions.append(
                                    _action(
                                        "set_approved_at",
                                        _subject_hash(lesson_id),
                                        {
                                            "status": "approved",
                                            "approved_at_missing": True,
                                            "approved_event_count": 1,
                                            "event_created_at": event_created_at,
                                        },
                                    )
                                )
                        else:
                            findings.append(
                                self._finding(
                                    "approved_at_missing_invalid_event_timestamp",
                                    "warning",
                                    "lesson",
                                    lesson_id,
                                    "review",
                                    {
                                        "approved_event_count": 1,
                                        "timestamp_valid": False,
                                    },
                                )
                            )
                    else:
                        findings.append(
                            self._finding(
                                "approved_at_missing_ambiguous",
                                "warning",
                                "lesson",
                                lesson_id,
                                "review",
                                {"approved_event_count": len(approved_events)},
                            )
                        )

                if status == "approved":
                    evidence_count = int(
                        connection.execute(
                            """
                            SELECT COUNT(*) FROM lesson_evidence
                            WHERE lesson_id = ?
                            """,
                            (lesson_id,),
                        ).fetchone()[0]
                    )
                    if evidence_count == 0:
                        findings.append(
                            self._finding(
                                "approved_without_evidence",
                                "warning",
                                "lesson",
                                lesson_id,
                                "review",
                                {"evidence_count": 0},
                            )
                        )

            findings.extend(self._legacy_findings(counts["lessons"]))
        except sqlite3.Error:
            return self._forbidden_audit(
                "database_unreadable",
                metadata={"readable": False},
            )
        finally:
            connection.close()

        findings.sort(
            key=lambda item: (
                item.code,
                item.subject_type,
                item.subject_id_hash,
            )
        )
        actions = tuple(rebuild_actions + timestamp_actions + rejection_actions)
        if any(finding.repair_class == "forbidden" for finding in findings):
            actions = ()
        return AuditReport(
            integrity=integrity,
            foreign_key_violations=foreign_key_violations,
            schema_version=schema_version,
            counts=counts,
            findings=tuple(findings),
            repair_plan=RepairPlan(actions),
        )

    @staticmethod
    def _lesson_for_hash(
        connection: sqlite3.Connection,
        subject_id_hash: str,
    ) -> sqlite3.Row | None:
        rows = connection.execute(
            """
            SELECT id, status, needs_reanalysis, title, category, approved_at
            FROM lessons
            """
        ).fetchall()
        matches = [
            row for row in rows if _subject_hash(str(row["id"])) == subject_id_hash
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _reject_precondition_matches(
        row: sqlite3.Row,
        expected: Metadata,
    ) -> bool:
        if str(row["status"]) != expected.get("status"):
            return False
        if expected.get("needs_reanalysis") is True and not bool(
            row["needs_reanalysis"]
        ):
            return False
        if expected.get("unknown_title") is True and not _is_unknown_title(
            row["title"]
        ):
            return False
        if expected.get("error_category") is True and _normalized(
            row["category"]
        ) != "error":
            return False
        return True

    @staticmethod
    def _lesson_metadata(row: sqlite3.Row | None) -> Metadata:
        if row is None:
            return {"subject_present": False}
        return {
            "subject_present": True,
            "status": str(row["status"]),
            "approved_at_missing": row["approved_at"] is None,
            "needs_reanalysis": bool(row["needs_reanalysis"]),
            "unknown_title": _is_unknown_title(row["title"]),
            "error_category": _normalized(row["category"]) == "error",
        }

    @staticmethod
    def _timestamp_metadata(row: sqlite3.Row | None) -> Metadata:
        if row is None:
            return {"subject_present": False}
        return {
            "subject_present": True,
            "approved_at_missing": row["approved_at"] is None,
        }

    @staticmethod
    def _outcome(
        action: RepairAction,
        *,
        status: ActionStatus,
        reason: Literal["applied", "already_applied", "precondition_failed"],
        before: Metadata,
        after: Metadata,
    ) -> ActionOutcome:
        return ActionOutcome(
            action_id=action.action_id,
            kind=action.kind,
            status=status,
            reason=reason,
            before=before,
            after=after,
        )

    def _apply_timestamp(
        self,
        connection: sqlite3.Connection,
        action: RepairAction,
    ) -> ActionOutcome:
        row = self._lesson_for_hash(connection, action.subject_id)
        before = self._timestamp_metadata(row)
        if row is None:
            return self._outcome(
                action,
                status="skipped",
                reason="precondition_failed",
                before=before,
                after=before,
            )
        expected = action.expected
        if row["approved_at"] is not None:
            reason = (
                "already_applied"
                if str(row["approved_at"]) == expected.get("event_created_at")
                else "precondition_failed"
            )
            return self._outcome(
                action,
                status="skipped",
                reason=reason,
                before=before,
                after=before,
            )
        if row["status"] != expected.get("status"):
            return self._outcome(
                action,
                status="skipped",
                reason="precondition_failed",
                before=before,
                after=before,
            )
        events = connection.execute(
            """
            SELECT created_at FROM lesson_events
            WHERE lesson_id = ? AND action = 'approved'
            ORDER BY id
            """,
            (row["id"],),
        ).fetchall()
        if len(events) != expected.get("approved_event_count"):
            return self._outcome(
                action,
                status="skipped",
                reason="precondition_failed",
                before=before,
                after=before,
            )
        event_created_at = str(events[0]["created_at"]) if len(events) == 1 else ""
        if event_created_at != expected.get("event_created_at"):
            return self._outcome(
                action,
                status="skipped",
                reason="precondition_failed",
                before=before,
                after=before,
            )
        connection.execute(
            """
            UPDATE lessons SET approved_at = ?
            WHERE id = ? AND approved_at IS NULL
            """,
            (event_created_at, row["id"]),
        )
        after = self._timestamp_metadata(
            self._lesson_for_hash(connection, action.subject_id)
        )
        return self._outcome(
            action,
            status="applied",
            reason="applied",
            before=before,
            after=after,
        )

    def _apply_rejection(
        self,
        connection: sqlite3.Connection,
        action: RepairAction,
    ) -> ActionOutcome:
        row = self._lesson_for_hash(connection, action.subject_id)
        before = self._lesson_metadata(row)
        if row is None:
            return self._outcome(
                action,
                status="skipped",
                reason="precondition_failed",
                before=before,
                after=before,
            )
        if row["status"] == "rejected":
            return self._outcome(
                action,
                status="skipped",
                reason="already_applied",
                before=before,
                after=before,
            )
        if not self._reject_precondition_matches(row, action.expected):
            return self._outcome(
                action,
                status="skipped",
                reason="precondition_failed",
                before=before,
                after=before,
            )
        results = self.store.apply_lifecycle_commands_in_transaction(
            connection,
            [
                LifecycleCommand(
                    "reject",
                    str(row["id"]),
                    LifecycleActor.system("data-health"),
                    reason="deterministic_data_health_rule",
                    expected_status=str(action.expected["status"]),
                )
            ],
        )
        after = self._lesson_metadata(
            self._lesson_for_hash(connection, action.subject_id)
        )
        if not results[0].changed:
            return self._outcome(
                action,
                status="skipped",
                reason="already_applied",
                before=before,
                after=after,
            )
        return self._outcome(
            action,
            status="applied",
            reason="applied",
            before=before,
            after=after,
        )

    def _apply_fts_rebuild(
        self,
        connection: sqlite3.Connection,
        action: RepairAction,
    ) -> ActionOutcome:
        drift, drift_hash = self._fts_drift(connection)
        before: Metadata = {
            "finding_count": len(drift),
            "drift_hash": drift_hash,
        }
        if not drift:
            return self._outcome(
                action,
                status="skipped",
                reason="already_applied",
                before=before,
                after=before,
            )
        if (
            drift_hash != action.expected.get("drift_hash")
            or len(drift) != action.expected.get("finding_count")
        ):
            return self._outcome(
                action,
                status="skipped",
                reason="precondition_failed",
                before=before,
                after=before,
            )
        connection.execute("DELETE FROM lesson_fts")
        rows = connection.execute(
            "SELECT id FROM lessons WHERE status = 'approved' ORDER BY id"
        ).fetchall()
        for row in rows:
            self.store._sync_fts(connection, str(row["id"]))
        after_drift, after_hash = self._fts_drift(connection)
        if after_drift:
            raise _RepairPostconditionFailed(
                "FTS rebuild postcondition failed: residual drift remains"
            )
        return self._outcome(
            action,
            status="applied",
            reason="applied",
            before=before,
            after={
                "finding_count": len(after_drift),
                "drift_hash": after_hash,
            },
        )

    @staticmethod
    def _validate_plan(actions: tuple[RepairAction, ...]) -> None:
        allowed = {"set_approved_at", "reject_lesson", "rebuild_fts"}
        if any(action.kind not in allowed for action in actions):
            raise ValueError("Repair plan contains a forbidden action")
        if len({action.action_id for action in actions}) != len(actions):
            raise ValueError("Repair plan contains duplicate action IDs")
        for action in actions:
            if (
                len(action.subject_id) != 64
                or any(character not in "0123456789abcdef" for character in action.subject_id)
            ):
                raise ValueError("Repair action subject must be a hashed ID")
            try:
                computed_id = _action(
                    action.kind,
                    action.subject_id,
                    action.expected,
                ).action_id
            except (TypeError, ValueError) as exc:
                raise ValueError("Repair action metadata is invalid") from exc
            if action.action_id != computed_id:
                raise ValueError("Repair action ID does not match its payload")

            keys = set(action.expected)
            if action.kind == "reject_lesson":
                allowed_keys = {"status"} | DEFECT_MARKERS
                recognized = {
                    marker
                    for marker in DEFECT_MARKERS
                    if action.expected.get(marker) is True
                }
                if not recognized:
                    raise ValueError(
                        "Reject action requires a deterministic defect marker"
                    )
                if keys - allowed_keys:
                    raise ValueError("Reject action has unknown preconditions")
                if action.expected.get("status") not in {
                    "pending",
                    "approved",
                }:
                    raise ValueError("Reject action has an invalid status")
            elif action.kind == "set_approved_at":
                if keys != {
                    "status",
                    "approved_at_missing",
                    "approved_event_count",
                    "event_created_at",
                }:
                    raise ValueError("Timestamp action has invalid preconditions")
                if (
                    action.expected.get("status") != "approved"
                    or action.expected.get("approved_at_missing") is not True
                    or action.expected.get("approved_event_count") != 1
                    or not isinstance(action.expected.get("event_created_at"), str)
                    or not _valid_timestamp(
                        str(action.expected.get("event_created_at") or "")
                    )
                ):
                    raise ValueError("Timestamp action has invalid preconditions")
            else:
                if keys != {"drift_hash", "finding_count"}:
                    raise ValueError("FTS action has invalid preconditions")
                drift_hash = action.expected.get("drift_hash")
                if (
                    not isinstance(drift_hash, str)
                    or len(drift_hash) != 64
                    or not isinstance(action.expected.get("finding_count"), int)
                    or int(action.expected["finding_count"]) <= 0
                ):
                    raise ValueError("FTS action has invalid preconditions")

    @staticmethod
    def _schema_precondition(
        connection: sqlite3.Connection,
    ) -> tuple[bool, Metadata]:
        try:
            schema_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
            table_names = {
                str(row["name"])
                for row in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table'
                    """
                ).fetchall()
            }
        except sqlite3.Error:
            return False, {
                "database_exists": True,
                "database_readable": False,
                "schema_compatible": False,
            }
        missing_tables = REQUIRED_TABLES - table_names
        compatible = (
            not missing_tables and schema_version == SCHEMA_VERSION
        )
        return compatible, {
            "database_exists": True,
            "database_readable": True,
            "schema_compatible": compatible,
            "schema_version": schema_version,
            "missing_table_count": len(missing_tables),
        }

    def _repair_preflight(
        self,
    ) -> tuple[bool, Metadata, tuple[int, int, int, int] | None]:
        if not self.database.path.is_file():
            return False, {
                "database_exists": False,
                "database_readable": False,
                "schema_compatible": False,
            }, None
        try:
            identity = self.database.path.stat()
            connection = self._read_only_connection()
        except (OSError, sqlite3.Error):
            return False, {
                "database_exists": True,
                "database_readable": False,
                "schema_compatible": False,
            }, None
        try:
            compatible, metadata = self._schema_precondition(connection)
        finally:
            connection.close()
        signature = (
            int(identity.st_dev),
            int(identity.st_ino),
            int(identity.st_size),
            int(identity.st_mtime_ns),
        )
        return compatible, metadata, signature

    @staticmethod
    def _precondition_report(
        actions: tuple[RepairAction, ...],
        metadata: Metadata,
    ) -> RepairReport:
        outcomes = tuple(
            ActionOutcome(
                action_id=action.action_id,
                kind=action.kind,
                status="skipped",
                reason="precondition_failed",
                before=dict(metadata),
                after=dict(metadata),
            )
            for action in actions
        )
        return RepairReport(
            planned_count=len(actions),
            applied_count=0,
            skipped_count=len(actions),
            applied_action_ids=(),
            skipped_action_ids=tuple(
                action.action_id for action in actions
            ),
            outcomes=outcomes,
        )

    def _open_existing_write_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.database.path.as_posix()}?mode=rw",
            uri=True,
            timeout=self.database.busy_timeout_ms / 1000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.database.busy_timeout_ms}")
        return connection

    def repair(self, plan: RepairPlan) -> RepairReport:
        actions = tuple(plan.actions)
        self._validate_plan(actions)
        if not actions:
            return RepairReport(
                planned_count=0,
                applied_count=0,
                skipped_count=0,
                applied_action_ids=(),
                skipped_action_ids=(),
                outcomes=(),
            )
        preflight_ok, preflight_metadata, preflight_signature = (
            self._repair_preflight()
        )
        if not preflight_ok:
            return self._precondition_report(actions, preflight_metadata)

        priority = {
            "rebuild_fts": 0,
            "set_approved_at": 1,
            "reject_lesson": 2,
        }
        indexed_actions = list(enumerate(actions))
        execution_order = sorted(
            indexed_actions,
            key=lambda item: (priority[item[1].kind], item[0]),
        )
        outcomes_by_index: dict[int, ActionOutcome] = {}
        try:
            connection = self._open_existing_write_connection()
        except sqlite3.Error:
            return self._precondition_report(
                actions,
                {
                    "database_exists": self.database.path.is_file(),
                    "database_readable": False,
                    "schema_compatible": False,
                },
            )
        try:
            compatible, writable_metadata = self._schema_precondition(connection)
            try:
                current = self.database.path.stat()
                current_signature = (
                    int(current.st_dev),
                    int(current.st_ino),
                    int(current.st_size),
                    int(current.st_mtime_ns),
                )
            except OSError:
                current_signature = None
            if (
                not compatible
                or current_signature is None
                or current_signature != preflight_signature
            ):
                return self._precondition_report(
                    actions,
                    {
                        **writable_metadata,
                        "database_identity_matches": (
                            current_signature == preflight_signature
                        ),
                    },
                )

            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.Error:
                return self._precondition_report(
                    actions,
                    {
                        **writable_metadata,
                        "database_identity_matches": False,
                    },
                )
            locked_compatible, locked_metadata = self._schema_precondition(
                connection
            )
            if not locked_compatible:
                connection.rollback()
                return self._precondition_report(
                    actions,
                    {
                        **locked_metadata,
                        "database_identity_matches": True,
                    },
                )
            try:
                locked = self.database.path.stat()
                locked_signature = (
                    int(locked.st_dev),
                    int(locked.st_ino),
                    int(locked.st_size),
                    int(locked.st_mtime_ns),
                )
            except OSError:
                locked_signature = None
            if locked_signature != preflight_signature:
                connection.rollback()
                return self._precondition_report(
                    actions,
                    {
                        **locked_metadata,
                        "database_identity_matches": False,
                    },
                )
            for index, action in execution_order:
                if action.kind == "set_approved_at":
                    outcome = self._apply_timestamp(connection, action)
                elif action.kind == "reject_lesson":
                    outcome = self._apply_rejection(connection, action)
                else:
                    outcome = self._apply_fts_rebuild(connection, action)
                outcomes_by_index[index] = outcome
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

        outcomes = tuple(
            outcomes_by_index[index] for index in range(len(actions))
        )
        applied = tuple(
            outcome.action_id
            for outcome in outcomes
            if outcome.status == "applied"
        )
        skipped = tuple(
            outcome.action_id
            for outcome in outcomes
            if outcome.status == "skipped"
        )

        return RepairReport(
            planned_count=len(actions),
            applied_count=len(applied),
            skipped_count=len(skipped),
            applied_action_ids=applied,
            skipped_action_ids=skipped,
            outcomes=outcomes,
        )
