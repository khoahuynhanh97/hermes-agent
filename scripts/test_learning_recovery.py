"""Regression checks for structured-learning recovery behavior."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.job_watcher import JobWorker
import core.knowledge_store as knowledge_store
from core.router import MODE_LEARN_KNOWLEDGE


def valid_proposal() -> dict:
    return {
        "title": "Reliable lesson",
        "category": "Technology",
        "hook_type": "result_hook",
        "cta_style": "soft",
        "voice_tone": "professional",
        "key_lessons": ["Use validated structured output before saving knowledge."],
        "summary": "A recovered summary produced from the saved source analysis.",
        "tools_and_concepts": "JSON validation",
        "workflow_steps": "Analyze, normalize once, validate, then save.",
        "hermes_applications": "Use for Telegram learning jobs.",
        "deep_analysis": "The saved analysis remains untrusted reference data.",
        "knowledge_type": "technology",
        "repositories": [],
        "ai_tools_or_skills": [],
        "search_keywords": [],
        "how_to_use_in_hermes": "Retrieve only after approval.",
    }


def run_normalization_check() -> None:
    worker = JobWorker()
    raw_analysis = "## Summary\n\nThe source explains safe structured knowledge extraction."
    with patch("core.job_watcher.ai_chat", return_value=json.dumps(valid_proposal())) as ai_chat:
        result = worker.normalize_knowledge_proposal(
            raw_response="This is not JSON.",
            analysis_text=raw_analysis,
            job_id="job_20260713_010203_abcdef",
        )

    assert result["summary"] == valid_proposal()["summary"]
    assert result["validation_status"] == "validated"
    assert ai_chat.call_count == 1
    assert "untrusted reference material" in ai_chat.call_args.args[0].lower()


def run_recoverability_check() -> None:
    worker = JobWorker()
    assert worker.is_recoverable_knowledge_failure("video_only", "high")
    assert worker.is_recoverable_knowledge_failure("transcript_only", "medium")
    assert not worker.is_recoverable_knowledge_failure("metadata_only", "low")
    assert not worker.is_recoverable_knowledge_failure("none", "medium")


def run_raw_recovery_payload_check() -> None:
    worker = JobWorker()
    payload = worker.build_raw_recovery_payload(
        raw_analysis="""# Analysis

## Summary

This video demonstrates a concise workflow for evaluating repositories.

- Keep raw source evidence.
- Approve lessons before retrieval.

## Details

More source material here.
""",
        fallback_title="Repository workflow",
    )
    assert payload["summary"].startswith("This video demonstrates")
    assert payload["key_lessons"] == [
        "Keep raw source evidence.",
        "Approve lessons before retrieval.",
    ]
    assert payload["needs_review"] is True
    assert payload["recovery_mode"] == "raw_analysis"


def run_store_reanalysis_state_check() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "knowledge_base"
        old_values = (
            knowledge_store.KB_DIR,
            knowledge_store.UNIFIED_INDEX_FILE,
            knowledge_store.ENTRIES_DIR,
        )
        knowledge_store.KB_DIR = root
        knowledge_store.UNIFIED_INDEX_FILE = root / "unified_index.json"
        knowledge_store.ENTRIES_DIR = root / "entries"
        knowledge_store.ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
        try:
            store = knowledge_store.UnifiedKnowledgeStore()
            entry = store.add_entry(
                title="Malformed JSON",
                source_url="https://example.com/video",
                detail_data={"summary": "Structured extraction failed."},
            )
            marked = store.mark_needs_reanalysis(
                entry["id"],
                "invalid JSON",
                {"original_job_id": "job_1", "raw_analysis": "Source-bound analysis"},
            )
            assert marked["needs_reanalysis"] is True
            detail = store.get_entry_detail(entry["id"])
            assert detail["validation_error"] == "invalid JSON"
            assert detail["reanalysis_count"] == 0
            assert detail["original_job_id"] == "job_1"
            assert knowledge_store.UnifiedKnowledgeStore().get_entry(entry["id"])["needs_reanalysis"] is True

            updated = store.replace_pending_lesson(
                entry["id"],
                {
                    "title": "Recovered lesson",
                    "category": "Technology",
                    "key_lessons": ["Use validated source evidence."],
                },
                {"summary": "Recovered from source analysis."},
            )
            assert updated["id"] == entry["id"]
            assert updated["status"] == "pending"
            assert updated["needs_reanalysis"] is False
            assert updated["title"] == "Recovered lesson"
            assert store.get_entry_detail(entry["id"])["summary"] == "Recovered from source analysis."
            persisted = knowledge_store.UnifiedKnowledgeStore().get_entry(entry["id"])
            assert persisted["needs_reanalysis"] is False
            assert persisted["title"] == "Recovered lesson"
        finally:
            (
                knowledge_store.KB_DIR,
                knowledge_store.UNIFIED_INDEX_FILE,
                knowledge_store.ENTRIES_DIR,
            ) = old_values


def run_worker_placeholder_check() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "knowledge_base"
        output_dir = Path(temp_dir) / "job_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        old_values = (
            knowledge_store.KB_DIR,
            knowledge_store.UNIFIED_INDEX_FILE,
            knowledge_store.ENTRIES_DIR,
        )
        knowledge_store.KB_DIR = root
        knowledge_store.UNIFIED_INDEX_FILE = root / "unified_index.json"
        knowledge_store.ENTRIES_DIR = root / "entries"
        knowledge_store.ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
        try:
            worker = JobWorker()
            entry = worker.create_reanalysis_placeholder(
                job={"job_id": "job_bad_json", "telegram": {"user_id": 123}},
                output_dir=output_dir,
                source_val="https://www.tiktok.com/@user/video/123",
                project_slug="tiktok-video-123",
                analysis_text="Source-bound transcript and visual analysis.",
                analysis_source="video_and_transcript",
                confidence="high",
                validation_error=ValueError("invalid JSON after normalization"),
            )
            persisted = knowledge_store.UnifiedKnowledgeStore().get_entry(entry["id"])
            detail = knowledge_store.UnifiedKnowledgeStore().get_entry_detail(entry["id"])
            assert persisted["status"] == "pending"
            assert persisted["needs_reanalysis"] is True
            assert detail["original_job_id"] == "job_bad_json"
            assert detail["raw_analysis"].startswith("Source-bound")
            assert detail["reanalysis_count"] == 0
            assert worker.is_recoverable_knowledge_failure("video_and_transcript", "high")
            assert not worker.is_recoverable_knowledge_failure("metadata_only", "low")
        finally:
            (
                knowledge_store.KB_DIR,
                knowledge_store.UNIFIED_INDEX_FILE,
                knowledge_store.ENTRIES_DIR,
            ) = old_values


def run_worker_reanalysis_update_check() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "knowledge_base"
        old_values = (
            knowledge_store.KB_DIR,
            knowledge_store.UNIFIED_INDEX_FILE,
            knowledge_store.ENTRIES_DIR,
        )
        knowledge_store.KB_DIR = root
        knowledge_store.UNIFIED_INDEX_FILE = root / "unified_index.json"
        knowledge_store.ENTRIES_DIR = root / "entries"
        knowledge_store.ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
        try:
            store = knowledge_store.UnifiedKnowledgeStore()
            success_entry = store.add_entry(
                title="Malformed success target",
                source_url="https://example.com/success",
                owner_user_id=123,
                detail_data={"raw_analysis": "Reliable saved source analysis."},
            )
            store.mark_needs_reanalysis(
                success_entry["id"],
                "invalid JSON",
                {
                    "raw_analysis": "Reliable saved source analysis.",
                    "analysis_source": "transcript_only",
                    "confidence": "medium",
                },
            )
            success_output = Path(temp_dir) / "success"
            success_job = {
                "job_id": "job_reanalysis_success",
                "source": {"value": "https://example.com/success", "transcript": "", "metadata": {}},
                "target": {"output_dir": str(success_output), "project_slug": "success"},
                "tasks": [MODE_LEARN_KNOWLEDGE, "analyze_video"],
                "style": {"notes": "", "language": "vi"},
                "telegram": {"user_id": 123},
                "reanalysis_target_id": success_entry["id"],
            }
            worker = JobWorker()
            with patch("core.job_watcher.load_profile", return_value={}), patch(
                "core.job_watcher.ai_chat", return_value=json.dumps(valid_proposal())
            ) as ai_chat:
                files, _ = worker.execute_job_tasks(success_job)
            persisted = knowledge_store.UnifiedKnowledgeStore().get_entry(success_entry["id"])
            assert ai_chat.call_count == 1
            assert persisted["id"] == success_entry["id"]
            assert persisted["title"] == valid_proposal()["title"]
            assert persisted["status"] == "pending"
            assert persisted["needs_reanalysis"] is False
            assert f"__KNOWLEDGE_ENTRY__:{success_entry['id']}" in files
            assert len(knowledge_store.UnifiedKnowledgeStore().list_entries()) == 1

            failed_entry = store.add_entry(
                title="Malformed failure target",
                source_url="https://example.com/failure",
                owner_user_id=123,
                detail_data={"raw_analysis": "Another reliable saved analysis."},
            )
            store.mark_needs_reanalysis(
                failed_entry["id"],
                "invalid JSON",
                {
                    "raw_analysis": "Another reliable saved analysis.",
                    "analysis_source": "video_only",
                    "confidence": "high",
                },
            )
            failed_job = {
                "job_id": "job_reanalysis_failure",
                "source": {"value": "https://example.com/failure", "transcript": "", "metadata": {}},
                "target": {"output_dir": str(Path(temp_dir) / "failure"), "project_slug": "failure"},
                "tasks": [MODE_LEARN_KNOWLEDGE, "analyze_video"],
                "style": {"notes": "", "language": "vi"},
                "telegram": {"user_id": 123},
                "reanalysis_target_id": failed_entry["id"],
            }
            with patch("core.job_watcher.load_profile", return_value={}), patch(
                "core.job_watcher.ai_chat", return_value="still not JSON"
            ) as ai_chat:
                files, _ = worker.execute_job_tasks(failed_job)
            failed = knowledge_store.UnifiedKnowledgeStore().get_entry(failed_entry["id"])
            failed_detail = knowledge_store.UnifiedKnowledgeStore().get_entry_detail(failed_entry["id"])
            assert ai_chat.call_count == 2
            assert failed["needs_reanalysis"] is True
            assert failed_detail["reanalysis_count"] == 1
            assert f"__KNOWLEDGE_ENTRY__:{failed_entry['id']}" in files
            assert len(knowledge_store.UnifiedKnowledgeStore().list_entries()) == 2
        finally:
            (
                knowledge_store.KB_DIR,
                knowledge_store.UNIFIED_INDEX_FILE,
                knowledge_store.ENTRIES_DIR,
            ) = old_values


def run_tests() -> None:
    run_normalization_check()
    run_recoverability_check()
    run_raw_recovery_payload_check()
    run_store_reanalysis_state_check()
    run_worker_placeholder_check()
    run_worker_reanalysis_update_check()
    print("learning recovery checks: PASS")


if __name__ == "__main__":
    run_tests()
