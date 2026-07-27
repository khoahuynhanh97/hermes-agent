from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes.db import Database


class LearningServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "hermes.db")
        self.database.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_lesson_without_evidence_is_rejected(self) -> None:
        from hermes.learning import LearningResult, LessonCandidate, SourceBundle

        result = LearningResult(
            source=SourceBundle(
                owner_user_id="42",
                source_type="youtube",
                source_key="youtube:one",
                source_url="https://youtube.com/watch?v=one",
                analysis_source="transcript_only",
                confidence="medium",
            ),
            summary="A source summary",
            deep_analysis="Analysis",
            evidence=[],
            lessons=[LessonCandidate(title="Lesson", summary="Reusable rule", evidence_indexes=[])],
        )

        with self.assertRaisesRegex(ValueError, "evidence"):
            result.validate()

    def test_metadata_only_result_keeps_summary_but_forbids_lessons(self) -> None:
        from hermes.learning import EvidenceItem, LearningResult, LessonCandidate, SourceBundle

        result = LearningResult(
            source=SourceBundle(
                owner_user_id="42",
                source_type="website",
                source_key="web:one",
                source_url="https://example.com",
                analysis_source="metadata_only",
                confidence="low",
            ),
            summary="Metadata summary",
            deep_analysis="",
            evidence=[EvidenceItem(kind="metadata", description="Page title")],
            lessons=[LessonCandidate(title="Unsupported", summary="Do not save", evidence_indexes=[0])],
        )

        with self.assertRaisesRegex(ValueError, "metadata-only"):
            result.validate()

        result.lessons = []
        result.validate()
        self.assertEqual(result.status, "summary_only")

    def test_atomic_lessons_are_persisted_under_one_source(self) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore
        from hermes.learning import EvidenceItem, LearningResult, LearningService, LessonCandidate, SourceBundle

        result = LearningResult(
            source=SourceBundle(
                owner_user_id="42",
                source_type="tiktok",
                source_key="upload:sha256:abc",
                local_path="D:/HermesData/artifacts/source.mp4",
                analysis_source="video_and_transcript",
                confidence="high",
            ),
            summary="The source explains two agent practices.",
            deep_analysis="Both practices reduce repeated context.",
            evidence=[
                EvidenceItem(kind="transcript", locator="00:01", excerpt="Create a repository map."),
                EvidenceItem(kind="transcript", locator="00:12", excerpt="Load only relevant files."),
            ],
            lessons=[
                LessonCandidate(
                    title="Create a repository map",
                    lesson_type="workflow",
                    category="technology",
                    summary="Map the repository before asking an agent to edit it.",
                    evidence_indexes=[0],
                ),
                LessonCandidate(
                    title="Load context selectively",
                    lesson_type="workflow",
                    category="technology",
                    summary="Load only files relevant to the current task.",
                    evidence_indexes=[1],
                ),
            ],
        )

        entries = LearningService(SQLiteKnowledgeStore(self.database)).persist_result(result, job_id="job-1")

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["source_id"], entries[1]["source_id"])
        self.assertEqual({entry["status"] for entry in entries}, {"pending"})
        self.assertIn("Create a repository map", SQLiteKnowledgeStore(self.database).get_entry_detail(entries[0]["id"])["evidence"][0]["excerpt"])

    def test_worker_builds_atomic_lessons_from_source_bound_analysis(self) -> None:
        from core.job_watcher import JobWorker

        result = JobWorker.build_learning_result(
            parsed={
                "title": "Agent context workflow",
                "category": "technology",
                "knowledge_type": "workflow",
                "summary": "The source explains two context practices.",
                "deep_analysis": "Use both practices together.",
                "key_lessons": ["Create a repository map", "Load only relevant files"],
                "search_keywords": ["agent context"],
                "repositories": [],
                "ai_tools_or_skills": [],
            },
            source_value="https://youtube.com/watch?v=one",
            owner_user_id="42",
            job_id="job-one",
            analysis_source="transcript_only",
            confidence="medium",
            transcript="At 00:01 create a repository map. At 00:12 load only relevant files.",
            analysis_text="Source-bound analysis",
            source_metadata={"title": "Tutorial"},
        )

        result.validate()
        self.assertEqual(len(result.lessons), 2)
        self.assertEqual(result.evidence[0].kind, "transcript")
        self.assertEqual(result.lessons[0].evidence_indexes, [0])


if __name__ == "__main__":
    unittest.main()
