from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SOURCE_BOUND_ANALYSIS = {
    "text_file",
    "document_text",
    "transcript_only",
    "audio_transcript",
    "photo_carousel",
    "image_vision",
    "video_only",
    "video_and_transcript",
}


@dataclass
class SourceBundle:
    owner_user_id: str
    source_type: str
    source_key: str
    source_url: str = ""
    local_path: str = ""
    title: str = ""
    analysis_source: str = "needs_source"
    confidence: str = "needs_source"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceItem:
    kind: str
    locator: str = ""
    excerpt: str = ""
    description: str = ""
    artifact_id: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "locator": self.locator,
            "excerpt": self.excerpt,
            "description": self.description,
            "artifact_id": self.artifact_id,
        }


@dataclass
class LessonCandidate:
    title: str
    summary: str
    lesson_type: str = "general"
    category: str = "General"
    content: str = ""
    key_lessons: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    confidence: str = "medium"
    evidence_indexes: list[int] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningResult:
    source: SourceBundle
    summary: str
    deep_analysis: str
    evidence: list[EvidenceItem]
    lessons: list[LessonCandidate]
    status: str = "pending_review"

    def validate(self) -> None:
        if not self.summary.strip():
            raise ValueError("Learning result requires a source summary")
        if self.source.analysis_source in {"metadata_only", "needs_source", "none"}:
            if self.lessons:
                raise ValueError("metadata-only or missing-source analysis cannot create lessons")
            self.status = "summary_only" if self.source.analysis_source == "metadata_only" else "needs_source"
            return
        if self.source.analysis_source not in SOURCE_BOUND_ANALYSIS:
            raise ValueError(f"Unsupported source-bound analysis type: {self.source.analysis_source}")
        if not self.evidence and self.lessons:
            raise ValueError("Every lesson requires source-bound evidence")
        for lesson in self.lessons:
            if not lesson.title.strip() or not lesson.summary.strip():
                raise ValueError("Lesson title and summary cannot be empty")
            if not lesson.evidence_indexes:
                raise ValueError(f"Lesson '{lesson.title}' has no evidence")
            if any(index < 0 or index >= len(self.evidence) for index in lesson.evidence_indexes):
                raise ValueError(f"Lesson '{lesson.title}' references invalid evidence")
        self.status = "pending_review" if self.lessons else "summary_only"


class LearningService:
    def __init__(self, knowledge_store):
        self.knowledge_store = knowledge_store

    def persist_result(self, result: LearningResult, job_id: str = "") -> list[dict]:
        result.validate()
        if not result.lessons:
            return []
        entries = []
        for lesson in result.lessons:
            selected_evidence = [result.evidence[index].as_dict() for index in lesson.evidence_indexes]
            details = {
                **lesson.extra,
                "lesson_type": lesson.lesson_type,
                "summary": lesson.summary,
                "deep_analysis": lesson.content or result.deep_analysis,
                "source_summary": result.summary,
                "analysis_source": result.source.analysis_source,
                "confidence": lesson.confidence or result.source.confidence,
                "tags": list(lesson.tags),
                "evidence": selected_evidence,
                "source_key": result.source.source_key,
                "source_metadata": {
                    **result.source.metadata,
                    "local_path": result.source.local_path,
                    "job_id": job_id,
                },
            }
            entry = self.knowledge_store.add_entry(
                title=lesson.title,
                source_url=result.source.source_url,
                platform=result.source.source_type,
                category=lesson.category,
                key_lessons=lesson.key_lessons or [lesson.summary],
                detail_data=details,
                source="learning_service",
                owner_user_id=result.source.owner_user_id,
                allow_multiple_source_lessons=True,
            )
            entries.append(entry)
        return entries
