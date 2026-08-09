"""Regression check for structured knowledge proposal lists."""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.job_watcher import JobWorker


def run_tests():
    worker = JobWorker()
    payload = {
        "title": "Spec kit",
        "key_lessons": ["Write a spec before implementation."],
        "repositories": [{"name": "spec-kit", "url": "https://github.com/example/spec-kit"}],
        "ai_tools_or_skills": [{"name": "specify-cli", "type": "tool"}],
        "search_keywords": [],
    }
    validated = worker.validate_extracted_json(
        payload,
        {
            "title": str,
            "key_lessons": list,
            "repositories": list,
            "ai_tools_or_skills": list,
            "search_keywords": list,
        },
        "knowledge_proposal",
        "job_test",
        list_item_types={
            "repositories": (str, dict),
            "ai_tools_or_skills": (str, dict),
        },
        allow_empty_lists={"repositories", "ai_tools_or_skills", "search_keywords"},
    )
    assert validated["repositories"][0]["name"] == "spec-kit"
    assert validated["ai_tools_or_skills"][0]["name"] == "specify-cli"
    assert validated["search_keywords"] == []
    print("knowledge structured output: PASS")


if __name__ == "__main__":
    run_tests()
