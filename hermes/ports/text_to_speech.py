"""Text-to-speech capability port."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TTSRequest:
    request_id: str
    text: str
    voice: str
    language: str = "vi-VN"
    style_prompt: str = ""


@dataclass
class TTSResult:
    request_id: str
    success: bool
    wav_path: str | None = None
    provider: str = ""
    model: str = ""
    voice: str = ""
    error_message: str = ""


class TextToSpeechPort(Protocol):
    def synthesize(self, request: TTSRequest) -> TTSResult:
        ...
