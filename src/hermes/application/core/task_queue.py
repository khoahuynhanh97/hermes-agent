import json
import shutil
from pathlib import Path

from hermes.application.core.artifact_store import ArtifactStore
from hermes.application.core.manifest import save_manifest, load_manifest, set_manifest_status, now_iso
from hermes.application.core.planner import plan_tasks, write_task_files
from hermes.application.core.status import apply_status_to_manifest, compute_progress


class TaskQueue:
    """Manifest-first file queue: jobs/{pending,running,done,failed}/job_id."""

    STATUSES = ["pending", "running", "done", "failed"]

    def __init__(self, jobs_root=None):
        repo_root = Path(__file__).resolve().parent.parent
        self.jobs_root = Path(jobs_root or repo_root / "jobs").resolve()
        self.pending_dir = self.jobs_root / "pending"
        self.running_dir = self.jobs_root / "running"
        self.done_dir = self.jobs_root / "done"
        self.failed_dir = self.jobs_root / "failed"
        self._ensure_dirs()

    def _ensure_dirs(self):
        for folder in [self.pending_dir, self.running_dir, self.done_dir, self.failed_dir]:
            folder.mkdir(parents=True, exist_ok=True)

    def create_job(self, manifest, metadata=None):
        job_id = manifest["job_id"]
        job_dir = self.pending_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "tasks").mkdir(exist_ok=True)
        (job_dir / "artifacts").mkdir(exist_ok=True)
        (job_dir / "logs").mkdir(exist_ok=True)

        metadata = metadata or {}
        if metadata:
            (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest = set_manifest_status(manifest, "planning")
        tasks = plan_tasks(manifest)
        manifest = apply_status_to_manifest(manifest, tasks)
        manifest["status"] = "pending"
        manifest["task_queue"] = {
            "job_dir": str(job_dir.resolve()),
            "tasks_dir": str((job_dir / "tasks").resolve()),
            "artifacts_dir": str((job_dir / "artifacts").resolve()),
            "logs_dir": str((job_dir / "logs").resolve()),
        }
        save_manifest(job_dir / "manifest.json", manifest)
        write_task_files(job_dir, manifest, tasks)
        self._log(job_dir, f"Created manifest job {job_id} with {len(tasks)} tasks.")
        return self.load_job(job_id)

    def list_jobs(self, limit=50):
        rows = []
        for queue_status, folder in [
            ("pending", self.pending_dir),
            ("running", self.running_dir),
            ("done", self.done_dir),
            ("failed", self.failed_dir),
        ]:
            for job_dir in folder.iterdir():
                if not job_dir.is_dir():
                    continue
                try:
                    data = self.load_job(job_dir.name, sync=True)
                    manifest = data["manifest"]
                    metadata = data.get("metadata", {})
                    progress = data.get("progress", {})
                    rows.append({
                        "job_id": manifest.get("job_id", job_dir.name),
                        "status": manifest.get("status", queue_status),
                        "queue_status": queue_status,
                        "created_at": manifest.get("created_at", ""),
                        "updated_at": manifest.get("updated_at", ""),
                        "project_slug": metadata.get("project_slug", ""),
                        "source": self._source_summary(manifest),
                        "engine": manifest.get("engine", ""),
                        "path": str(job_dir.resolve()),
                        "progress": progress,
                    })
                except Exception:
                    continue
        rows.sort(key=lambda item: item.get("updated_at") or item.get("created_at", ""), reverse=True)
        return rows[:limit]

    def load_job(self, job_id, sync=False):
        job_dir = self.find_job_dir(job_id)
        if not job_dir:
            raise FileNotFoundError(f"Manifest job not found: {job_id}")
        manifest = load_manifest(job_dir / "manifest.json")
        tasks = self.load_tasks(job_dir)
        metadata = self._read_json(job_dir / "metadata.json", default={})
        store = ArtifactStore(job_dir)
        artifacts = store.sync_from_files(tasks)
        if sync:
            changed = False
            for task in tasks:
                if task.get("status") in ["done", "completed"]:
                    continue
                output_file = task.get("output_file")
                if output_file and store.has_artifact(output_file):
                    task["status"] = "done"
                    task["completed_at"] = now_iso()
                    changed = True
            if changed:
                self.save_tasks(job_dir, tasks)
            manifest["artifacts"] = artifacts
            manifest = apply_status_to_manifest(manifest, tasks)
            save_manifest(job_dir / "manifest.json", manifest)
            self._move_for_manifest_status(job_dir, manifest.get("status"))
            job_dir = self.find_job_dir(job_id) or job_dir
        return {
            "job_dir": str(job_dir.resolve()),
            "manifest": manifest,
            "tasks": tasks,
            "artifacts": artifacts,
            "metadata": metadata,
            "progress": compute_progress(tasks),
        }

    def load_tasks(self, job_dir):
        tasks_dir = Path(job_dir) / "tasks"
        tasks = []
        for path in sorted(tasks_dir.glob("task_*.json")):
            try:
                tasks.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return tasks

    def save_tasks(self, job_dir, tasks):
        tasks_dir = Path(job_dir) / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        for task in tasks:
            path = tasks_dir / f"{task['task_id']}.json"
            path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")

    def mark_task_running(self, job_id, task_id):
        return self._update_task(job_id, task_id, {"status": "running", "started_at": now_iso(), "error": ""})

    def mark_task_done(self, job_id, task_id):
        return self._update_task(job_id, task_id, {"status": "done", "completed_at": now_iso(), "error": ""})

    def mark_task_failed(self, job_id, task_id, error):
        return self._update_task(job_id, task_id, {"status": "failed", "completed_at": now_iso(), "error": error})

    def find_job_dir(self, job_id):
        for folder in [self.pending_dir, self.running_dir, self.done_dir, self.failed_dir]:
            candidate = folder / job_id
            if candidate.exists():
                return candidate
        return None

    def _update_task(self, job_id, task_id, fields):
        job_dir = self.find_job_dir(job_id)
        if not job_dir:
            raise FileNotFoundError(job_id)
        tasks = self.load_tasks(job_dir)
        for task in tasks:
            if task.get("task_id") == task_id:
                task.update(fields)
                break
        self.save_tasks(job_dir, tasks)
        manifest = load_manifest(job_dir / "manifest.json")
        manifest = apply_status_to_manifest(manifest, tasks)
        save_manifest(job_dir / "manifest.json", manifest)
        self._move_for_manifest_status(job_dir, manifest.get("status"))
        return self.load_job(job_id, sync=True)

    def _move_for_manifest_status(self, job_dir, status):
        job_dir = Path(job_dir)
        if status == "completed":
            target_parent = self.done_dir
        elif status == "failed":
            target_parent = self.failed_dir
        elif status == "running":
            target_parent = self.running_dir
        else:
            target_parent = self.pending_dir
        if job_dir.parent == target_parent:
            return job_dir
        target = target_parent / job_dir.name
        if target.exists():
            return target
        shutil.move(str(job_dir), str(target))
        return target

    def _source_summary(self, manifest):
        input_data = manifest.get("input", {})
        return (
            input_data.get("tiktok_url")
            or input_data.get("reference_video")
            or input_data.get("product_name")
            or manifest.get("objective", "")
        )

    def _log(self, job_dir, line):
        log_path = Path(job_dir) / "logs" / "system.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{now_iso()} {line}\n")

    def _read_json(self, path, default=None):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return default
