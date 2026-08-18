from dataclasses import dataclass
from pathlib import Path


@dataclass
class ManualWorkerResult:
    handled: bool
    message: str
    artifact_path: str = ""


class BaseWorker:
    """Base contract for future automatic Hermes workers."""

    worker_name = "base"

    def can_handle(self, task):
        return task.get("worker") == self.worker_name

    def run(self, job_dir, manifest, task):
        prompt_path = Path(job_dir) / task.get("prompt_file", "")
        return ManualWorkerResult(
            handled=False,
            message=(
                f"Worker '{self.worker_name}' is manual for now. "
                f"Read {prompt_path} and write artifacts/{task.get('output_file')}."
            ),
        )
