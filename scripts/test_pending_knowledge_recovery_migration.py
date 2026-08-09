"""Regression checks for repairing old pending placeholder lessons."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.job_watcher import JobWorker
from scripts.recover_pending_knowledge import build_recovered_entry, build_needs_source_entry


def valid_proposal() -> dict:
    return {
        "title": "Recovered workflow",
        "category": "Technology",
        "hook_type": "result_hook",
        "cta_style": "soft",
        "voice_tone": "professional",
        "key_lessons": ["Keep the raw source before approval."],
        "summary": "A verified summary from the previously saved structured response.",
        "tools_and_concepts": "Structured output",
        "workflow_steps": "Validate and save.",
        "hermes_applications": "Use in the learning workflow.",
        "deep_analysis": "Only approved lessons are retrievable.",
        "knowledge_type": "technology",
        "repositories": [],
        "ai_tools_or_skills": [],
        "search_keywords": [],
        "how_to_use_in_hermes": "Review before approval.",
    }


def run_tests() -> None:
    worker = JobWorker()
    entry = {
        "id": "kb_fixture",
        "title": "Placeholder",
        "status": "pending",
        "source_url": "https://example.com/video",
        "platform": "youtube",
        "job_output_dir": "C:/fixture",
        "key_lessons": ["See the detailed report"],
    }
    repaired_entry, repaired_detail, report = build_recovered_entry(
        entry=entry,
        raw_response=json.dumps(valid_proposal()),
        raw_analysis="## Summary\n\nSource-grounded analysis.",
        analysis_source="video_only",
        confidence="high",
        worker=worker,
    )
    assert repaired_entry["title"] == "Recovered workflow"
    assert repaired_entry["status"] == "pending"
    assert repaired_detail["validation_status"] == "recovered_from_raw_response"
    assert repaired_detail["summary"] == valid_proposal()["summary"]
    assert "verified summary" in report.lower()

    needs_source_entry, needs_source_detail = build_needs_source_entry(entry, "metadata_only")
    assert needs_source_entry["status"] == "pending"
    assert needs_source_entry["key_lessons"] == ["Gửi video gốc, transcript, hoặc file upload để Hermes học nguồn này đáng tin cậy."]
    assert needs_source_detail["needs_source"] is True
    print("pending knowledge recovery migration checks: PASS")


if __name__ == "__main__":
    run_tests()
