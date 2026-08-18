"""End-to-end worker fixture for metadata-only learning analysis."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from hermes.application.core.job_watcher import JobWorker


def run_tests():
    with TemporaryDirectory() as tmp:
        job = {
            "job_id": "fixture_metadata_job",
            "job_type": "tiktok_product_review",
            "engine": "ai_studio",
            "source": {
                "value": "https://www.youtube.com/watch?v=fixture",
                "metadata": {
                    "title": "Fixture tutorial",
                    "description": "A short public description",
                },
            },
            "tasks": ["analyze_video"],
            "style": {"language": "vi", "notes": "Analyze only what the source supports."},
            "target": {"output_dir": tmp, "project_slug": "fixture"},
        }
        worker = JobWorker()
        with patch.object(worker, "_resolve_media_for_analysis", return_value=None), patch(
            "core.job_watcher.ai_chat", return_value="Analysis based on metadata only."
        ) as mocked:
            files, summary = worker.execute_job_tasks(job)

        assert "analysis.md" in files
        assert "Analysis based on metadata only." in (Path(tmp) / "analysis.md").read_text(encoding="utf-8")
        assert mocked.call_args_list[0].kwargs["task_type"] == "analysis"
        assert "LOW-CONFIDENCE" in mocked.call_args_list[0].args[0]
        assert "Analysis based on metadata only." in summary
    print("metadata-only learning job fixture: PASS")


if __name__ == "__main__":
    run_tests()
