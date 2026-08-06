"""Factory for selecting TTS provider implementations."""
from __future__ import annotations

import os
import wave
from pathlib import Path

from hermes.ports.text_to_speech import TextToSpeechPort, TTSRequest, TTSResult


class FakeTTSProvider(TextToSpeechPort):
    def __init__(self, output_dir: str | None = None):
        if os.environ.get("HERMES_ALLOW_FAKE_PROVIDERS", "").strip() != "1":
            raise ValueError("TTS_PROVIDER=fake selected but HERMES_ALLOW_FAKE_PROVIDERS is not set")
        configured = output_dir or os.environ.get("HERMES_TTS_OUTPUT_DIR", "")
        self.output_dir = Path(configured).expanduser().resolve() if configured else (Path.cwd() / "audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def synthesize(self, request: TTSRequest) -> TTSResult:
        safe = "".join(c for c in request.request_id if c.isalnum() or c in "-_.") or "voiceover"
        wav_path = self.output_dir / f"{safe}.wav"
        sample_rate = 24000
        num_samples = sample_rate
        silence = b"\x00\x00" * num_samples
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(silence)
        return TTSResult(
            request_id=request.request_id,
            success=True,
            wav_path=str(wav_path),
            provider="fake",
            model="fake-tts",
            voice=request.voice,
        )


def get_tts_provider(output_dir: str | None = None) -> TextToSpeechPort:
    provider = os.environ.get("TTS_PROVIDER", "google_vertex").strip().lower()
    if provider == "fake":
        return FakeTTSProvider(output_dir=output_dir)
    elif provider in ("google_vertex", "vertex"):
        from providers.vertex_tts_provider import GoogleVertexTTSProvider
        return GoogleVertexTTSProvider(output_dir=output_dir)
    else:
        raise ValueError(f"unsupported TTS_PROVIDER: {provider}")
