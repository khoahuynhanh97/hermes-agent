from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .application.knowledge_lifecycle import LifecycleActor, LifecycleCommand
from .db import Database
from .knowledge import SQLiteKnowledgeStore


Severity = Literal["info", "warning", "error"]
RepairClass = Literal["safe", "review", "forbidden"]
RepairKind = Literal["rebuild_fts", "set_approved_at", "reject_lesson"]
Metadata = dict[str, int | str | bool]


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
class RepairReport:
    planned_count: int
    applied_count: int
    skipped_count: int
    applied_action_ids: tuple[str, ...]
    skipped_action_ids: tuple[str, ...]


def _subject_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalized(value: str | None) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().casefold()


def _json_list(value: str | None) -> list:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


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
        tags = " ".join(str(item) for item in _json_list(row["tags_json"]))
        key_lessons = "\n".join(
            str(item) for item in _json_list(row["key_lessons_json"])
        )
        return (
            str(row["id"]),
            str(row["owner_user_id"]),
            str(row["title"]),
            str(row["summary"]),
            f"{row['content']}\n{key_lessons}",
            tags,
        )

    @classmethod
    def _fts_drift(
        cls,
        connection: sqlite3.Connection,
    ) -> tuple[list[tuple[str, str]], str]:
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

        drift: list[tuple[str, str]] = []
        drift_preconditions: list[tuple[str, str, str, str]] = []
        approved_ids = {
            lesson_id
            for lesson_id, row in lessons.items()
            if row["status"] == "approved"
        }
        for lesson_id in sorted(approved_ids):
            actual = actual_by_id.get(lesson_id, [])
            expected = cls._expected_fts(lessons[lesson_id])
            if not actual:
                drift.append(("fts_missing", lesson_id))
                drift_preconditions.append(
                    (
                        "fts_missing",
                        _subject_hash(lesson_id),
                        "",
                        _subject_hash(json.dumps(expected, ensure_ascii=False)),
                    )
                )
            elif len(actual) != 1 or actual[0] != expected:
                drift.append(("fts_mismatch", lesson_id))
                drift_preconditions.append(
                    (
                        "fts_mismatch",
                        _subject_hash(lesson_id),
                        _subject_hash(json.dumps(actual, ensure_ascii=False)),
                        _subject_hash(json.dumps(expected, ensure_ascii=False)),
                    )
                )

        for lesson_id in sorted(actual_by_id):
            if lesson_id not in lessons:
                drift.append(("fts_orphan", lesson_id))
                drift_preconditions.append(
                    (
                        "fts_orphan",
                        _subject_hash(lesson_id),
                        _subject_hash(
                            json.dumps(actual_by_id[lesson_id], ensure_ascii=False)
                        ),
                        "",
                    )
                )
            elif lesson_id not in approved_ids:
                drift.append(("fts_extra", lesson_id))
                drift_preconditions.append(
                    (
                        "fts_extra",
                        _subject_hash(lesson_id),
                        _subject_hash(
                            json.dumps(actual_by_id[lesson_id], ensure_ascii=False)
                        ),
                        "",
                    )
                )

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

    def audit(self) -> AuditReport:
        findings: list[Finding] = []
        timestamp_actions: list[RepairAction] = []
        rejection_actions: list[RepairAction] = []
        rebuild_actions: list[RepairAction] = []

        connection = self._read_only_connection()
        try:
            integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
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

            schema_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
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
            for code, lesson_id in drift:
                findings.append(
                    self._finding(
                        code,
                        "error",
                        "lesson_fts",
                        lesson_id,
                        "safe",
                        {"row_count": 1},
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
                                "approved_at_missing_ambiguous",
                                "warning",
                                "lesson",
                                lesson_id,
                                "review",
                                {"approved_event_count": len(approved_events)},
                            )
                        )

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
                if _normalized(row["title"]) == _normalized("Không xác định"):
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
                if len(defect_expected) > 1 and status != "rejected":
                    rejection_actions.append(
                        _action(
                            "reject_lesson",
                            _subject_hash(lesson_id),
                            defect_expected,
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
        finally:
            connection.close()

        findings.sort(
            key=lambda item: (
                item.code,
                item.subject_type,
                item.subject_id_hash,
            )
        )
        actions = tuple(timestamp_actions + rejection_actions + rebuild_actions)
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
        if expected.get("unknown_title") is True and _normalized(
            row["title"]
        ) != _normalized("Không xác định"):
            return False
        if expected.get("error_category") is True and _normalized(
            row["category"]
        ) != "error":
            return False
        return True

    def _apply_timestamp(
        self,
        connection: sqlite3.Connection,
        action: RepairAction,
    ) -> bool:
        row = self._lesson_for_hash(connection, action.subject_id)
        if row is None or row["approved_at"] is not None:
            return False
        expected = action.expected
        if row["status"] != expected.get("status"):
            return False
        events = connection.execute(
            """
            SELECT created_at FROM lesson_events
            WHERE lesson_id = ? AND action = 'approved'
            ORDER BY id
            """,
            (row["id"],),
        ).fetchall()
        if len(events) != expected.get("approved_event_count"):
            return False
        event_created_at = str(events[0]["created_at"]) if len(events) == 1 else ""
        if event_created_at != expected.get("event_created_at"):
            return False
        connection.execute(
            """
            UPDATE lessons SET approved_at = ?, updated_at = ?
            WHERE id = ? AND approved_at IS NULL
            """,
            (event_created_at, event_created_at, row["id"]),
        )
        return True

    def _apply_rejection(
        self,
        connection: sqlite3.Connection,
        action: RepairAction,
    ) -> bool:
        row = self._lesson_for_hash(connection, action.subject_id)
        if row is None or row["status"] == "rejected":
            return False
        if not self._reject_precondition_matches(row, action.expected):
            return False
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
        return bool(results[0].changed)

    def _apply_fts_rebuild(
        self,
        connection: sqlite3.Connection,
        action: RepairAction,
    ) -> bool:
        drift, drift_hash = self._fts_drift(connection)
        if not drift or drift_hash != action.expected.get("drift_hash"):
            return False
        connection.execute("DELETE FROM lesson_fts")
        rows = connection.execute(
            "SELECT id FROM lessons WHERE status = 'approved' ORDER BY id"
        ).fetchall()
        for row in rows:
            self.store._sync_fts(connection, str(row["id"]))
        return True

    def repair(self, plan: RepairPlan) -> RepairReport:
        actions = tuple(plan.actions)
        allowed = {"set_approved_at", "reject_lesson", "rebuild_fts"}
        if any(action.kind not in allowed for action in actions):
            raise ValueError("Repair plan contains a forbidden action")
        if len({action.action_id for action in actions}) != len(actions):
            raise ValueError("Repair plan contains duplicate action IDs")

        applied: list[str] = []
        skipped: list[str] = []
        with self.database.transaction(immediate=True) as connection:
            for action in actions:
                if action.kind == "set_approved_at":
                    changed = self._apply_timestamp(connection, action)
                elif action.kind == "reject_lesson":
                    changed = self._apply_rejection(connection, action)
                else:
                    changed = self._apply_fts_rebuild(connection, action)
                (applied if changed else skipped).append(action.action_id)

        return RepairReport(
            planned_count=len(actions),
            applied_count=len(applied),
            skipped_count=len(skipped),
            applied_action_ids=tuple(applied),
            skipped_action_ids=tuple(skipped),
        )
