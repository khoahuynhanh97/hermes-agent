import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from core.file_manager import to_slug
from core.manifest import create_manifest, now_iso
from core.project_manager import ProjectManager
from core.task_queue import TaskQueue


DEFAULT_TASKS = [
    "analyze_video",
    "write_script",
    "write_image_prompts",
    "write_voiceover",
    "write_capcut_plan",
]


class AgentJobManager:
    """File-based job queue for external AI workers such as Antigravity or Codex."""

    def __init__(self, project_manager=None, jobs_root=None):
        self.project_manager = project_manager or ProjectManager()
        repo_root = Path(__file__).resolve().parent.parent
        self.jobs_root = Path(jobs_root or repo_root / ".agent_jobs").resolve()
        self.task_queue = TaskQueue(repo_root / "jobs")
        self.inbox_dir = self.jobs_root / "inbox"
        self.processing_dir = self.jobs_root / "processing"
        self.outbox_dir = self.jobs_root / "outbox"
        self.failed_dir = self.jobs_root / "failed"
        self._ensure_dirs()

    def _ensure_dirs(self):
        for folder in [self.inbox_dir, self.processing_dir, self.outbox_dir, self.failed_dir]:
            folder.mkdir(parents=True, exist_ok=True)

    def create_job(
        self,
        source_value,
        source_kind="auto",
        target_mode="create_new",
        target_project_slug=None,
        new_project_name=None,
        tasks=None,
        style=None,
        created_by="hermes_gui",
        telegram_info=None,
        engine="ai_studio",
        job_type="tiktok_product_review",
        constraints=None,
        product_color="",
        product_images=None,
        expected_outputs=None,
    ):
        source_value = (source_value or "").strip()
        if not source_value:
            raise ValueError("source_value is required")

        tasks = tasks or DEFAULT_TASKS
        style = style or {}
        job_id = self._new_job_id()
        source_kind = self._detect_source_kind(source_value, source_kind)

        project_path, project_slug = self._resolve_target_project(
            source_value=source_value,
            target_mode=target_mode,
            target_project_slug=target_project_slug,
            new_project_name=new_project_name,
        )
        folders = self.project_manager.get_project_folders(project_slug)
        output_dir = Path(folders["root"]) / "agent_outputs" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat(timespec="seconds")
        job = {
            "schema_version": 1,
            "job_id": job_id,
            "status": "pending",
            "created_at": now,
            "created_by": created_by,
            "engine": engine,
            "job_type": job_type,
            "source": {
                "kind": source_kind,
                "value": source_value,
            },
            "telegram": telegram_info or {},
            "target": {
                "mode": target_mode,
                "project_slug": project_slug,
                "project_path": str(Path(project_path).resolve()),
                "output_dir": str(output_dir.resolve()),
            },
            "tasks": tasks,
            "style": {
                "language": style.get("language", "vi"),
                "video_format": style.get("video_format", "vertical_tiktok"),
                "duration_seconds": int(style.get("duration_seconds") or 45),
                "notes": style.get("notes", ""),
            },
            "expected_outputs": expected_outputs or [
                "analysis.md",
                "product_lock.md",
                "script.md",
                "scenes.json",
                "image_prompts.md",
                "video_prompts.md",
                "workflow.json",
                "voiceover.txt",
                "capcut_plan.md",
                "worker_notes.md",
            ],
        }

        product_name = (new_project_name or "").strip() or self._derive_project_name(source_value)
        manifest_input = {
            "product_name": product_name,
            "product_color": product_color or "",
            "product_images": product_images or [],
            "reference_video": source_value if source_kind in ["local_video", "url"] else "",
            "tiktok_url": source_value if source_kind == "tiktok_url" else "",
            "language": job["style"]["language"],
            "target_platform": "tiktok",
        }
        manifest = create_manifest(
            job_id=job_id,
            job_type=job_type,
            engine=engine,
            input_data=manifest_input,
            objective=style.get("notes") or "Create a TikTok content package",
            constraints=constraints,
            outputs_required=expected_outputs,
        )
        manifest_job = self.task_queue.create_job(
            manifest,
            metadata={
                "created_by": created_by,
                "project_slug": project_slug,
                "project_path": str(Path(project_path).resolve()),
                "legacy_output_dir": str(output_dir.resolve()),
                "telegram": telegram_info or {},
                "source": job["source"],
            },
        )

        worker_prompt_path = output_dir / "antigravity_codex_prompt.md"
        self._write_worker_prompt(job, worker_prompt_path)
        job["paths"] = {
            "job_file": str((self.inbox_dir / f"{job_id}.json").resolve()),
            "worker_prompt": str(worker_prompt_path.resolve()),
            "done_file": str((self.outbox_dir / f"{job_id}.done.json").resolve()),
            "manifest_job_dir": manifest_job["job_dir"],
            "manifest_file": str((Path(manifest_job["job_dir"]) / "manifest.json").resolve()),
            "manifest_worker_prompt": str((Path(manifest_job["job_dir"]) / "worker_prompt.md").resolve()),
        }
        job["manifest"] = manifest_job["manifest"]
        job["manifest_tasks"] = manifest_job["tasks"]

        self._write_json(self.inbox_dir / f"{job_id}.json", job)
        self._write_json(output_dir / "job.json", job)
        self._append_project_job(project_slug, job)
        return job

    def mark_processing(self, job_id):
        """Move job from inbox to processing."""
        inbox_file = self.inbox_dir / f"{job_id}.json"
        if not inbox_file.exists():
            return None
        job = self._read_json(inbox_file)
        job["status"] = "processing"
        job["updated_at"] = datetime.now().isoformat(timespec="seconds")
        
        proc_file = self.processing_dir / f"{job_id}.json"
        self._write_json(proc_file, job)
        try:
            inbox_file.unlink()
        except Exception:
            pass
        
        out_dir = Path(job["target"]["output_dir"])
        if out_dir.exists():
            self._write_json(out_dir / "job.json", job)
        return job

    def complete_job(self, job_id, summary="", files_created=None):
        """Complete job and save result into outbox as {job_id}.done.json."""
        proc_file = self.processing_dir / f"{job_id}.json"
        inbox_file = self.inbox_dir / f"{job_id}.json"
        
        job = None
        if proc_file.exists():
            job = self._read_json(proc_file)
            try: proc_file.unlink()
            except Exception: pass
        elif inbox_file.exists():
            job = self._read_json(inbox_file)
            try: inbox_file.unlink()
            except Exception: pass
            
        if not job:
            out_file = self.outbox_dir / f"{job_id}.done.json"
            if out_file.exists():
                return self._read_json(out_file)
            raise ValueError(f"Job {job_id} not found in processing or inbox")

        now = datetime.now().isoformat(timespec="seconds")
        job["status"] = "done"
        job["completed_at"] = now
        job["summary"] = summary
        job["files_created"] = files_created or []

        done_file = self.outbox_dir / f"{job_id}.done.json"
        self._write_json(done_file, job)

        out_dir = Path(job["target"]["output_dir"])
        if out_dir.exists():
            self._write_json(out_dir / "job.json", job)
            self._sync_manifest_artifacts(job, files_created or [], out_dir)
            
        self._update_project_job_status(job["target"]["project_slug"], job_id, "done")
        return job

    def fail_job(self, job_id, error_message=""):
        """Mark job as failed."""
        proc_file = self.processing_dir / f"{job_id}.json"
        inbox_file = self.inbox_dir / f"{job_id}.json"
        
        job = None
        for p in [proc_file, inbox_file]:
            if p.exists():
                job = self._read_json(p)
                try: p.unlink()
                except Exception: pass
                break
                
        if not job:
            return None

        job["status"] = "failed"
        job["error"] = error_message
        job["failed_at"] = datetime.now().isoformat(timespec="seconds")
        
        fail_file = self.failed_dir / f"{job_id}.failed.json"
        self._write_json(fail_file, job)
        self._update_project_job_status(job["target"]["project_slug"], job_id, "failed")
        return job

    def get_outbox_results(self):
        """Get all unarchived done jobs from outbox."""
        results = []
        for path in self.outbox_dir.glob("*.done.json"):
            try:
                data = self._read_json(path)
                output_dir = data.get("output_dir") or data.get("target", {}).get("output_dir", "")
                if output_dir:
                    job_json = Path(output_dir) / "job.json"
                    if job_json.exists():
                        original_job = self._read_json(job_json)
                        data.setdefault("telegram", original_job.get("telegram", {}))
                        data.setdefault("target", original_job.get("target", {}))
                        data.setdefault("source", original_job.get("source", {}))
                if "target" not in data:
                    data["target"] = {
                        "project_slug": data.get("project_slug", ""),
                        "output_dir": output_dir,
                    }
                results.append(data)
            except Exception:
                continue
        for row in self.task_queue.list_jobs(limit=100):
            if row.get("queue_status") != "done":
                continue
            try:
                data = self.task_queue.load_job(row["job_id"], sync=True)
                metadata = data.get("metadata", {})
                if metadata.get("telegram_dispatched"):
                    continue
                telegram_info = metadata.get("telegram", {})
                if not telegram_info:
                    continue
                manifest = data["manifest"]
                artifacts = data.get("artifacts", [])
                results.append({
                    "job_id": manifest.get("job_id"),
                    "status": "done",
                    "summary": f"Manifest job completed: {manifest.get('objective', '')}",
                    "files_created": [item.get("name") for item in artifacts if item.get("name")],
                    "telegram": telegram_info,
                    "target": {
                        "project_slug": metadata.get("project_slug", ""),
                        "output_dir": str((Path(data["job_dir"]) / "artifacts").resolve()),
                    },
                    "source": metadata.get("source", {}),
                    "manifest": manifest,
                })
            except Exception:
                continue
        return results

    def archive_done_job(self, job_id):
        """Archive done job from outbox after Telegram bot has dispatched it."""
        done_file = self.outbox_dir / f"{job_id}.done.json"
        archive_dir = self.jobs_root / "done_archived"
        archive_dir.mkdir(parents=True, exist_ok=True)
        if done_file.exists():
            dest = archive_dir / done_file.name
            dest.write_text(done_file.read_text(encoding="utf-8"), encoding="utf-8")
            try:
                done_file.unlink()
            except Exception:
                pass
        manifest_dir = self.task_queue.find_job_dir(job_id)
        if manifest_dir:
            meta_path = Path(manifest_dir) / "metadata.json"
            meta = self._read_json(meta_path) if meta_path.exists() else {}
            meta["telegram_dispatched"] = True
            meta["telegram_dispatched_at"] = now_iso()
            self._write_json(meta_path, meta)

    def _update_project_job_status(self, project_slug, job_id, status):
        try:
            meta = self.project_manager.get_metadata(project_slug) or {}
            jobs = meta.get("agent_jobs", [])
            for j in jobs:
                if j.get("job_id") == job_id:
                    j["status"] = status
            self.project_manager.save_metadata(project_slug, meta)
        except Exception:
            pass

    def list_jobs(self, limit=30):
        rows = []
        seen = set()
        for item in self.task_queue.list_jobs(limit=limit):
            seen.add(item["job_id"])
            rows.append({
                "job_id": item["job_id"],
                "status": item["status"],
                "queue_status": item.get("queue_status", ""),
                "created_at": item.get("created_at", ""),
                "project_slug": item.get("project_slug", ""),
                "source": item.get("source", ""),
                "engine": item.get("engine", ""),
                "path": item.get("path", ""),
                "progress": item.get("progress", {}),
                "manifest_job": True,
            })
        for status, folder in [
            ("pending", self.inbox_dir),
            ("processing", self.processing_dir),
            ("done", self.outbox_dir),
            ("failed", self.failed_dir),
        ]:
            for path in folder.glob("*.json"):
                try:
                    data = self._read_json(path)
                except Exception:
                    continue
                if data.get("job_id") in seen:
                    continue
                rows.append({
                    "job_id": data.get("job_id", path.stem.replace(".done", "")),
                    "status": data.get("status", status),
                    "created_at": data.get("created_at", ""),
                    "project_slug": data.get("target", {}).get("project_slug", ""),
                    "source": data.get("source", {}).get("value", ""),
                    "path": str(path.resolve()),
                })
        rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return rows[:limit]

    def load_manifest_job(self, job_id, sync=True):
        return self.task_queue.load_job(job_id, sync=sync)

    def _sync_manifest_artifacts(self, job, files_created, source_dir):
        manifest_job_dir = job.get("paths", {}).get("manifest_job_dir", "")
        if not manifest_job_dir:
            return
        job_dir = Path(manifest_job_dir)
        artifacts_dir = job_dir / "artifacts"
        if not job_dir.exists():
            return
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        copied = False
        for name in files_created:
            if not name:
                continue
            source_file = Path(source_dir) / name
            if not source_file.exists() or not source_file.is_file():
                continue
            shutil.copy2(str(source_file), str(artifacts_dir / source_file.name))
            copied = True

        if copied:
            try:
                self.task_queue.load_job(job["job_id"], sync=True)
            except Exception:
                pass

    def _resolve_target_project(self, source_value, target_mode, target_project_slug, new_project_name):
        if target_mode == "append_existing":
            if not target_project_slug:
                raise ValueError("target_project_slug is required for append_existing")
            project_path = self.project_manager.get_project_folders(target_project_slug)["root"]
            if not os.path.exists(project_path):
                raise ValueError(f"Project not found: {target_project_slug}")
            return project_path, target_project_slug

        project_name = (new_project_name or "").strip() or self._derive_project_name(source_value)
        return self.project_manager.initialize_project(project_name)

    def _append_project_job(self, project_slug, job):
        meta = self.project_manager.get_metadata(project_slug) or {}
        meta.setdefault("agent_jobs", [])
        meta["agent_jobs"].append({
            "job_id": job["job_id"],
            "status": job["status"],
            "created_at": job["created_at"],
            "source": job["source"],
            "output_dir": job["target"]["output_dir"],
            "worker_prompt": job["paths"]["worker_prompt"],
            "manifest_job_dir": job["paths"].get("manifest_job_dir", ""),
            "manifest_worker_prompt": job["paths"].get("manifest_worker_prompt", ""),
        })
        self.project_manager.save_metadata(project_slug, meta)

    def _write_worker_prompt(self, job, path):
        tasks = "\n".join(f"- {task}" for task in job["tasks"])
        expected = "\n".join(f"- {name}" for name in job["expected_outputs"])
        done_file = self.outbox_dir / f"{job['job_id']}.done.json"
        if job.get("engine") == "upgrade_audit" or job.get("job_type") == "hermes_upgrade_audit":
            prompt = f"""# Hermes Upgrade Audit Bridge

You are working with Hermes, Codex, and Antigravity through file artifacts.

Do not implement code changes in this job. This job is only for analysis,
cross-review, and a human-approved upgrade proposal.

Job ID: {job['job_id']}
Source type: {job['source']['kind']}
Source value: {job['source']['value']}
Project folder: {job['target']['project_path']}
Output folder: {job['target']['output_dir']}
Manifest worker prompt: {job.get('paths', {}).get('manifest_worker_prompt', '')}
Notes: {job['style'].get('notes', '')}

## Collaboration flow
1. Codex inspects the Hermes repo and writes `upgrade_audit.md`.
2. Antigravity reads `upgrade_audit.md` and writes `antigravity_review.md`.
3. Codex reads both files and writes `upgrade_proposal.md`.
4. Codex writes `approval_checklist.md`.
5. The user checks and approves before any implementation job starts.

## Required output files
{expected}

## Output rules
- Write all generated files inside the output folder only.
- Do not edit app code, production prompts, approved lessons, or config files.
- Call out assumptions and unknowns instead of guessing.
- Keep the proposal practical for this local Hermes app.
- Use Vietnamese without accents if your editor has encoding issues.

## Completion marker
After writing the output files, create this JSON file:
{done_file.resolve()}

The done JSON should include: job_id, status="done", project_slug, output_dir, files_created, summary.
"""
            path.write_text(prompt, encoding="utf-8")
            return

        prompt = f"""# Hermes Agent Worker Prompt

You are the AI worker for Hermes TikTok Video Factory.

Read the job JSON and produce the requested files. Do not overwrite unrelated project files.

Job ID: {job['job_id']}
Source type: {job['source']['kind']}
Source value: {job['source']['value']}
Project folder: {job['target']['project_path']}
Output folder: {job['target']['output_dir']}
Language: {job['style']['language']}
Format: {job['style']['video_format']}
Target duration: {job['style']['duration_seconds']} seconds
Notes: {job['style'].get('notes', '')}

## Tasks
{tasks}

## Required output files
{expected}

## Output rules
- Write all generated files inside the output folder only.
- Use Vietnamese for creator-facing content unless the task explicitly asks for English prompts.
- Keep scene prompts suitable for vertical 9:16 TikTok/CapCut workflows.
- For image/video prompts, include one prompt per scene and avoid unsupported claims.
- If source analysis is incomplete, state assumptions in worker_notes.md.

## Completion marker
After writing the output files, create this JSON file:
{done_file.resolve()}

The done JSON should include: job_id, status="done", project_slug, output_dir, files_created, summary.
"""
        path.write_text(prompt, encoding="utf-8")

    def _derive_project_name(self, source_value):
        cleaned = re.sub(r"https?://", "", source_value.strip(), flags=re.I)
        cleaned = re.sub(r"[^A-Za-z0-9]+", " ", cleaned).strip()
        if not cleaned:
            cleaned = "agent video job"
        cleaned = cleaned[:80]
        slug = to_slug(cleaned)
        return slug.replace("-", " ") or "agent video job"

    def _detect_source_kind(self, source_value, source_kind):
        if source_kind and source_kind != "auto":
            return source_kind
        lowered = source_value.lower()
        if lowered.startswith("http") and "tiktok" in lowered:
            return "tiktok_url"
        if lowered.startswith("http"):
            return "url"
        return "local_video"

    def _new_job_id(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"job_{stamp}_{uuid4().hex[:6]}"

    def _write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_json(self, path):
        return json.loads(path.read_text(encoding="utf-8"))
