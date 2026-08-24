from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Sequence

from hermes_personal.learning.models import LearningCandidate, LearningVersion

UNSAFE_SKILL_PATTERNS = [
    re.compile(r"rm\s+-rf", re.IGNORECASE),
    re.compile(r"curl\s+.*\|\s*(?:bash|sh)", re.IGNORECASE),
    re.compile(r"wget\s+.*\|\s*(?:bash|sh)", re.IGNORECASE),
    re.compile(r"\b(?:eval|exec)\s*\(", re.IGNORECASE),
    re.compile(r"os\.system\s*\(", re.IGNORECASE),
]


class ProceduralSkillPublisher:
    """Publishes approved procedural learning versions into valid upstream SKILL.md projections with rollback safety."""

    def __init__(
        self,
        output_dir: Path | str,
        default_allowed_capabilities: Sequence[str] = ("product.research", "product.resource_pack.build"),
    ) -> None:
        self.output_dir = Path(output_dir)
        self.default_allowed_capabilities = tuple(default_allowed_capabilities)

    def _sanitize_skill_name(self, name: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower())
        return clean.strip("-") or "procedural-skill"

    def _check_safety(self, content: str) -> None:
        for pat in UNSAFE_SKILL_PATTERNS:
            if pat.search(content):
                raise ValueError(f"Unsafe executable command detected matching pattern '{pat.pattern}'")

    def publish(
        self,
        candidate: LearningCandidate,
        version: LearningVersion,
        allowed_capabilities: Sequence[str] | None = None,
    ) -> Path:
        if candidate.kind != "procedure":
            raise ValueError(f"Only procedure candidates can be published as skills (got '{candidate.kind}')")
        if version.status != "active":
            raise ValueError(f"Only active versions can be published as skills (got '{version.status}')")

        self._check_safety(candidate.content)
        self._check_safety(version.content)

        caps = tuple(allowed_capabilities) if allowed_capabilities is not None else self.default_allowed_capabilities
        skill_name = self._sanitize_skill_name(candidate.title)
        skill_dir = self.output_dir / skill_name
        version_dir = skill_dir / "versions" / str(version.version)
        version_dir.mkdir(parents=True, exist_ok=True)

        caps_yaml = "\n".join(f"  - {cap}" for cap in caps)

        skill_md_content = f"""---
name: {skill_name}
description: {candidate.title}
version: {version.version}
owner: {version.owner_user_id}
digest: {version.digest}
allowed-capabilities:
{caps_yaml}
---

# {candidate.title}

## Procedural Instructions
{version.content}

## Governance & Provenance
- **Candidate ID**: {candidate.candidate_id}
- **Version ID**: {version.version_id}
- **Version**: {version.version}
- **Owner User ID**: {version.owner_user_id}
- **Content Digest**: {version.digest}
"""

        # 1. Write versioned file
        version_file = version_dir / "SKILL.md"
        with open(version_file, "w", encoding="utf-8") as f:
            f.write(skill_md_content)

        # 2. Atomically write active root SKILL.md
        active_file = skill_dir / "SKILL.md"
        self._atomic_write(active_file, skill_md_content)

        # 3. Update manifest
        manifest_file = skill_dir / "manifest.json"
        manifest_data = {
            "skill_name": skill_name,
            "candidate_id": candidate.candidate_id,
            "active_version": version.version,
            "active_version_id": version.version_id,
            "digest": version.digest,
            "updated_at": version.created_at,
        }
        self._atomic_write(manifest_file, json.dumps(manifest_data, indent=2))

        return active_file

    def rollback(
        self,
        skill_name: str,
        prior_candidate: LearningCandidate | None = None,
        prior_version: LearningVersion | None = None,
    ) -> Path | None:
        clean_name = self._sanitize_skill_name(skill_name)
        skill_dir = self.output_dir / clean_name

        if prior_candidate is not None and prior_version is not None:
            # Re-publish the prior version as active
            return self.publish(prior_candidate, prior_version)

        # No prior version: remove active projection
        active_file = skill_dir / "SKILL.md"
        if active_file.exists():
            active_file.unlink()

        manifest_file = skill_dir / "manifest.json"
        if manifest_file.exists():
            manifest_data = {
                "skill_name": clean_name,
                "active_version": None,
                "active_version_id": None,
                "status": "rolled_back_empty",
            }
            self._atomic_write(manifest_file, json.dumps(manifest_data, indent=2))

        return None

    def _atomic_write(self, target_path: Path, content: str) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_file = tempfile.mkstemp(dir=str(target_path.parent), prefix="tmp_skill_")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
            # Atomic replace
            os.replace(tmp_file, target_path)
        except Exception:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
            raise
