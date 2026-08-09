"""Verify local text attachments use the text learning fallback."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.job_watcher import JobWorker


def run_tests():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "lesson.md"
        source.write_text("# Token saving\nCompress repeated context before an agent call.", encoding="utf-8")
        job = {
            "job_id": "local_text_fixture",
            "job_type": "knowledge_learning",
            "engine": "ai_studio",
            "source": {"value": str(source)},
            "tasks": ["analyze_video"],
            "style": {"language": "vi", "notes": "Read the attached text."},
            "target": {"output_dir": str(root / "output"), "project_slug": "local-text"},
        }
        job["target"]["output_dir"] = str(root / "output")
        Path(job["target"]["output_dir"]).mkdir()
        worker = JobWorker()
        with patch("core.job_watcher.ai_chat", return_value="Text source analysis") as mocked:
            files, summary = worker.execute_job_tasks(job)
        assert "analysis.md" in files
        assert "Text source analysis" in (root / "output" / "analysis.md").read_text(encoding="utf-8")
        prompt = mocked.call_args_list[0].args[0]
        assert "Compress repeated context" in prompt
        assert "DỮ LIỆU THAM CHIẾU" in prompt
        assert "Text source analysis" in summary
    print("local text learning tests: PASS")


if __name__ == "__main__":
    run_tests()
