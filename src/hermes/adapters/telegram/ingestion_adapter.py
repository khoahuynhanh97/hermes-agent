from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hermes.application.ingestion_service import IngestionService
from hermes.domain.ingestion import IngestionRequest
from hermes.domain.results import Result


@dataclass(frozen=True)
class FakeTelegramVideo:
    file_id: str
    caption: str = ""


@dataclass(frozen=True)
class FakeTelegramDocument:
    file_id: str
    file_name: str = ""


_ACTION_MAP: dict[str, str] = {
    "/hoc_kien_thuc": "learn_knowledge",
    "/hoc_hook_CTA": "learn_hook_cta",
    "/len_kich_ban": "create_script",
    "/hoc_video": "learn_video",
}


class TelegramIngestionAdapter:
    def __init__(self, service: IngestionService):
        self.service = service

    def handle_video(self, video: FakeTelegramVideo) -> Result[IngestionRequest]:
        caption = getattr(video, "caption", "") or ""
        requested_action = self._extract_action(caption)
        return self.service.submit(
            source=video.file_id,
            source_type="video",
            requested_action=requested_action,
            payload={"caption": caption, "file_id": video.file_id},
        )

    def handle_document(self, doc: FakeTelegramDocument) -> Result[IngestionRequest]:
        return self.service.submit(
            source=doc.file_id,
            source_type="document",
            requested_action="ingest_document",
            payload={"file_name": doc.file_name, "file_id": doc.file_id},
        )

    def _extract_action(self, caption: str) -> str:
        for prefix, action in _ACTION_MAP.items():
            if caption.strip().startswith(prefix):
                return action
        return "ingest_generic"