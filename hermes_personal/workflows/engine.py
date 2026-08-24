from __future__ import annotations

import json
import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List

from .repository import WorkflowRepository, DuplicateCommandError, VersionConflict
from .models import IllegalTransition


@dataclass(frozen=True)
class CommandResult:
    workflow_id: str
    new_version: int
    success: bool = True
    message: str | None = None


class WorkflowEngine:
    """Idempotent command handling for a workflow aggregate.

    Stores workflow state in a simple in‑memory dict and persists events via
    ``WorkflowRepository``. Duplicate commands are detected via the repository's
    ``processed_command`` table and replayed without side effects.
    """

    _state_machine: Dict[str, List[str]] = {
        "initial": ["started"],
        "started": ["approval_requested", "cancelled", "expired"],
        "approval_requested": ["approved", "rejected", "cancelled", "expired"],
        "approved": ["job_dispatched", "cancelled", "expired"],
        "job_dispatched": ["job_succeeded", "job_failed", "cancelled", "expired"],
        "job_failed": ["job_retried", "cancelled", "expired"],
        "job_retried": ["job_succeeded", "job_failed", "cancelled", "expired"],
        "cancelled": [],
        "expired": [],
    }

    def __init__(self, repository: WorkflowRepository) -> None:
        self.repo = repository
        # in‑memory workflow state: {workflow_id: {"state": str, "version": int}}
        self._cache: Dict[str, Dict[str, Any]] = {}

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def handle(self, command: Dict[str, Any]) -> CommandResult:
        """Process a command dictionary.

        Expected keys::
            command_id   – unique identifier for idempotency
            workflow_id  – target workflow
            type         – command type (e.g. "start")
            args         – optional payload
        """
        cmd_id = command.get("command_id")
        wf_id = command.get("workflow_id", "default")
        cmd_type = command.get("type")
        args = command.get("args", {})
        if not cmd_id or not cmd_type:
            raise ValueError("command_id and type are required")

        # Duplicate detection – repository will raise DuplicateCommandError.
        try:
            events = self._build_events(wf_id, cmd_id, cmd_type, args)
        except DuplicateCommandError:
            # Fetch current version without mutating state.
            version = self._cache.get(wf_id, {}).get("version", 0)
            return CommandResult(workflow_id=wf_id, new_version=version, message="duplicate")

        # Persist via repository.
        aggregate_json = json.dumps(self._cache.get(wf_id, {}))
        try:
            result = self.repo.commit_workflow(
                workflow_id=wf_id,
                aggregate_json=aggregate_json,
                events=events,
                expected_version=self._cache.get(wf_id, {}).get("version"),
            )
        except VersionConflict as exc:
            raise exc
        # Update in‑memory cache.
        self._cache.setdefault(wf_id, {"state": "initial", "version": 0})
        self._apply_state_transition(wf_id, cmd_type, args)
        self._cache[wf_id]["version"] = result.new_version
        return CommandResult(workflow_id=wf_id, new_version=result.new_version)

    def get_workflow_state(self, workflow_id: str) -> tuple[str, int] | None:
        """Get state and version from cache or underlying repository."""
        if workflow_id in self._cache:
            entry = self._cache[workflow_id]
            return entry.get("state", "initial"), entry.get("version", 0)
        wf_data = self.repo.get_workflow(workflow_id)
        if wf_data is not None:
            aggregate_dict, version = wf_data
            state = aggregate_dict.get("state", "initial")
            self._cache[workflow_id] = {"state": state, "version": version}
            return state, version
        return None

    def set_workflow_state(self, workflow_id: str, state: str, version: int = 1) -> None:
        """Helper to register/update workflow state directly for tests or execution."""
        self._cache[workflow_id] = {"state": state, "version": version}
        try:
            with self.repo.conn:
                cur = self.repo.conn.cursor()
                cur.execute(
                    "INSERT INTO workflow (workflow_id, aggregate_json, version) VALUES (?, ?, ?) "
                    "ON CONFLICT(workflow_id) DO UPDATE SET aggregate_json=excluded.aggregate_json, version=excluded.version",
                    (workflow_id, json.dumps({"state": state}), version),
                )
        except Exception:
            pass

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _build_events(
        self, workflow_id: str, command_id: str, cmd_type: str, args: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Create event dicts for the repository layer.

        Detects duplicate commands via ``processed_command`` before creating any
        events.
        """
        # Check duplicate via repository directly.
        # This will raise DuplicateCommandError if already present.
        # We perform a cheap SELECT using the repo's connection.
        cur = self.repo.conn.cursor()
        cur.execute(
            "SELECT command_id FROM processed_command WHERE workflow_id = ? AND command_id = ?",
            (workflow_id, command_id),
        )
        if cur.fetchone():
            raise DuplicateCommandError()
        # Build a single event representing the command.
        event = {
            "event_id": str(uuid.uuid4()),
            "command_id": command_id,
            "event_type": self._event_type_for_command(cmd_type),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "payload": args,
        }
        return [event]

    def _event_type_for_command(self, cmd_type: str) -> str:
        mapping = {
            "start": "WorkflowStarted",
            "record_artifact": "ArtifactRecorded",
            "request_approval": "ApprovalRequested",
            "approve": "Approved",
            "reject": "Rejected",
            "dispatch_job": "JobDispatched",
            "job_succeeded": "JobSucceeded",
            "job_failed": "JobFailed",
            "retry": "JobRetried",
            "cancel": "Cancelled",
            "expire": "Expired",
        }
        return mapping.get(cmd_type, "Unknown")

    def _apply_state_transition(self, wf_id: str, cmd_type: str, args: Dict[str, Any]) -> None:
        # Simple state machine mapping command to new state.
        transition_map = {
            "start": "started",
            "record_artifact": "started",
            "request_approval": "approval_requested",
            "approve": "approved",
            "reject": "cancelled",
            "dispatch_job": "job_dispatched",
            "job_succeeded": "job_dispatched",  # stay in dispatched until further cmds
            "job_failed": "job_failed",
            "retry": "job_retried",
            "cancel": "cancelled",
            "expire": "expired",
        }
        new_state = transition_map.get(cmd_type)
        if new_state is None:
            raise IllegalTransition(self._cache.get(wf_id, {}).get("state", "initial"), "unknown", "unsupported command")
        current_state = self._cache.get(wf_id, {}).get("state", "initial")
        allowed = self._state_machine.get(current_state, [])
        if new_state not in allowed:
            raise IllegalTransition(current_state, new_state, f"command {cmd_type} not allowed")
        # Update state.
        self._cache.setdefault(wf_id, {"state": "initial", "version": 0})["state"] = new_state
