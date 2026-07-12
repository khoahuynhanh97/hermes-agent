from core.manifest import now_iso


DONE_TASK_STATUSES = {"done", "completed", "skipped"}


def normalize_task_status(status):
    if status == "completed":
        return "done"
    return status or "pending"


def compute_progress(tasks):
    total = len(tasks or [])
    if total == 0:
        return {"done": 0, "total": 0, "percent": 0}

    done = sum(1 for task in tasks if normalize_task_status(task.get("status")) in DONE_TASK_STATUSES)
    return {"done": done, "total": total, "percent": round((done / total) * 100, 2)}


def compute_job_status(tasks, failed=False):
    if failed:
        return "failed"
    if not tasks:
        return "pending"

    statuses = [normalize_task_status(task.get("status")) for task in tasks]
    if any(status == "failed" for status in statuses):
        return "failed"
    if all(status in DONE_TASK_STATUSES for status in statuses):
        return "completed"
    if any(status == "running" for status in statuses):
        return "running"
    return "pending"


def apply_status_to_manifest(manifest, tasks):
    manifest["tasks"] = tasks
    manifest["progress"] = compute_progress(tasks)
    manifest["status"] = compute_job_status(tasks)
    manifest["updated_at"] = now_iso()
    return manifest
