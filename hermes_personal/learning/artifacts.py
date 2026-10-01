from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


@dataclass(frozen=True)
class SourceArtifactRecord:
    artifact_id: str
    candidate_id: str
    owner_user_id: str
    kind: str  # "video" | "audio" | "transcript" | "analysis" | "manifest" | "document"
    filename: str
    relative_path: str
    sha256: str
    size_bytes: int
    mime_type: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "candidate_id": self.candidate_id,
            "owner_user_id": self.owner_user_id,
            "kind": self.kind,
            "filename": self.filename,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "created_at": self.created_at,
        }


class SourceArtifactStore:
    """Manages durable storage and indexing of raw media/files for knowledge candidates."""

    def __init__(self, connection: Any, base_dir: Path | str | None = None) -> None:
        self._conn = connection
        if base_dir is None:
            self._base_dir = Path(get_hermes_home()) / "knowledge" / "sources"
        else:
            self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def store_file(
        self,
        candidate_id: str,
        owner_user_id: str,
        source_path: Path | str,
        kind: str,
        mime_type: str = "",
    ) -> SourceArtifactRecord:
        src = Path(source_path)
        if not src.is_file():
            raise FileNotFoundError(f"Source file not found: {src}")

        # Compute SHA-256 and size
        hasher = hashlib.sha256()
        size = 0
        with open(src, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
                size += len(chunk)
        digest = hasher.hexdigest()

        artifact_id = f"art_{uuid.uuid4().hex[:12]}"
        dest_dir = self._base_dir / candidate_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_filename = f"{kind}_{src.name}"
        dest_path = dest_dir / dest_filename
        shutil.copy2(src, dest_path)

        relative_path = str(dest_path.relative_to(self._base_dir))
        now = datetime.now(timezone.utc).isoformat()

        record = SourceArtifactRecord(
            artifact_id=artifact_id,
            candidate_id=candidate_id,
            owner_user_id=owner_user_id,
            kind=kind,
            filename=dest_filename,
            relative_path=relative_path,
            sha256=digest,
            size_bytes=size,
            mime_type=mime_type,
            created_at=now,
        )

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO source_artifact (
                    artifact_id, candidate_id, owner_user_id, kind,
                    filename, relative_path, sha256, size_bytes, mime_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.artifact_id,
                    record.candidate_id,
                    record.owner_user_id,
                    record.kind,
                    record.filename,
                    record.relative_path,
                    record.sha256,
                    record.size_bytes,
                    record.mime_type,
                    record.created_at,
                ),
            )

        return record

    def list_artifacts_for_candidate(self, candidate_id: str) -> tuple[SourceArtifactRecord, ...]:
        rows = self._conn.execute(
            "SELECT * FROM source_artifact WHERE candidate_id = ? ORDER BY created_at ASC",
            (candidate_id,),
        ).fetchall()
        return tuple(
            SourceArtifactRecord(
                artifact_id=r["artifact_id"] if hasattr(r, "keys") else r[0],
                candidate_id=r["candidate_id"] if hasattr(r, "keys") else r[1],
                owner_user_id=r["owner_user_id"] if hasattr(r, "keys") else r[2],
                kind=r["kind"] if hasattr(r, "keys") else r[3],
                filename=r["filename"] if hasattr(r, "keys") else r[4],
                relative_path=r["relative_path"] if hasattr(r, "keys") else r[5],
                sha256=r["sha256"] if hasattr(r, "keys") else r[6],
                size_bytes=r["size_bytes"] if hasattr(r, "keys") else r[7],
                mime_type=r["mime_type"] if hasattr(r, "keys") else r[8],
                created_at=r["created_at"] if hasattr(r, "keys") else r[9],
            )
            for r in rows
        )
