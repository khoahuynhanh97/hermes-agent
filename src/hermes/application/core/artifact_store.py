import json
from datetime import datetime
from pathlib import Path


ARTIFACTS_FILE = "artifacts.json"


def _now():
    return datetime.now().isoformat(timespec="seconds")


class ArtifactStore:
    """File-backed artifact metadata helper for a single manifest job."""

    def __init__(self, job_dir):
        self.job_dir = Path(job_dir)
        self.artifacts_dir = self.job_dir / "artifacts"
        self.meta_path = self.job_dir / ARTIFACTS_FILE
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        if not self.meta_path.exists():
            self._write_meta([])

    def write_artifact(self, name, content, created_by_task="", artifact_type=None):
        artifact_path = self.artifacts_dir / name
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            artifact_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
            artifact_type = artifact_type or "json"
        else:
            artifact_path.write_text(str(content), encoding="utf-8")
            artifact_type = artifact_type or self._infer_type(name)

        return self.register_artifact(name, created_by_task=created_by_task, artifact_type=artifact_type)

    def register_artifact(self, name, created_by_task="", artifact_type=None):
        artifacts = self.list_artifacts()
        rel_path = f"artifacts/{name}"
        entry = {
            "name": name,
            "type": artifact_type or self._infer_type(name),
            "path": rel_path,
            "created_by_task": created_by_task,
            "created_at": _now(),
        }
        artifacts = [item for item in artifacts if item.get("name") != name]
        artifacts.append(entry)
        self._write_meta(artifacts)
        return entry

    def sync_from_files(self, tasks=None):
        task_by_output = {}
        for task in tasks or []:
            output_file = task.get("output_file")
            if output_file:
                task_by_output[output_file] = task.get("task_id", "")

        artifacts = self.list_artifacts()
        known = {item.get("name") for item in artifacts}
        changed = False
        for path in self.artifacts_dir.iterdir():
            if not path.is_file() or path.name in known:
                continue
            artifacts.append({
                "name": path.name,
                "type": self._infer_type(path.name),
                "path": f"artifacts/{path.name}",
                "created_by_task": task_by_output.get(path.name, ""),
                "created_at": _now(),
            })
            changed = True
        if changed:
            self._write_meta(artifacts)
        return artifacts

    def read_artifact(self, name):
        path = self.artifacts_dir / name
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def has_artifact(self, name):
        return (self.artifacts_dir / name).exists()

    def artifact_path(self, name):
        return self.artifacts_dir / name

    def list_artifacts(self):
        if not self.meta_path.exists():
            return []
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write_meta(self, artifacts):
        self.meta_path.write_text(json.dumps(artifacts, ensure_ascii=False, indent=2), encoding="utf-8")

    def _infer_type(self, name):
        suffix = Path(name).suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix in [".md", ".txt"]:
            return "markdown" if suffix == ".md" else "text"
        if suffix in [".mp4", ".mov", ".webm"]:
            return "video"
        if suffix in [".png", ".jpg", ".jpeg", ".webp"]:
            return "image"
        if suffix in [".wav", ".mp3", ".m4a"]:
            return "audio"
        return "file"
