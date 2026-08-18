"""Factory for selecting TTS provider implementations."""
from __future__ import annotations

import os
from pathlib import Path

from hermes.ports.text_to_speech import TextToSpeechPort, TTSRequest, TTSResult


class EdgeTTSProvider(TextToSpeechPort):
    def __init__(self, output_dir: str | None = None):
        configured = output_dir or os.environ.get("HERMES_TTS_OUTPUT_DIR", "")
        self.output_dir = Path(configured).expanduser().resolve() if configured else (Path.cwd() / "audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def synthesize(self, request: TTSRequest) -> TTSResult:
        from hermes.tools.tts_engine import synthesize_edge_tts
        safe = "".join(c for c in request.request_id if c.isalnum() or c in "-_.") or "voiceover"
        wav_path = self.output_dir / f"{safe}.mp3"
        voice_choice = request.voice if request.voice and "Neural" in request.voice else "vi-VN-HoaiMyNeural"
        try:
            result_path = synthesize_edge_tts(
                request.text,
                voice=voice_choice,
                speed=1.0,
                output_path=str(wav_path)
            )
            if not Path(result_path).is_file() or Path(result_path).stat().st_size < 1000:
                raise RuntimeError("Edge TTS output file is missing or empty")
            return TTSResult(
                request_id=request.request_id,
                success=True,
                wav_path=result_path,
                provider="edge_tts",
                model="ms-edge-neural",
                voice=voice_choice,
            )
        except Exception as err:
            raise RuntimeError(f"TTS_SYNTHESIS_FAILED: Real Vietnamese voiceover generation failed: {err}")


class FakeTTSProvider(TextToSpeechPort):
    def __init__(self, output_dir: str | None = None):
        if os.environ.get("HERMES_ALLOW_FAKE_PROVIDERS", "").strip() != "1":
            raise ValueError("TTS_PROVIDER=fake selected but HERMES_ALLOW_FAKE_PROVIDERS is not set")
        configured = output_dir or os.environ.get("HERMES_TTS_OUTPUT_DIR", "")
        self.output_dir = Path(configured).expanduser().resolve() if configured else (Path.cwd() / "audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def synthesize(self, request: TTSRequest) -> TTSResult:
        import wave
        safe = "".join(c for c in request.request_id if c.isalnum() or c in "-_.") or "voiceover"
        wav_path = self.output_dir / f"{safe}.wav"
        sample_rate = 24000
        num_samples = sample_rate * 5
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
    provider = os.environ.get("TTS_PROVIDER", "edge_tts").strip().lower()
    if provider in ("google_vertex", "vertex"):
        try:
            from hermes.integrations.providers.vertex_tts_provider import GoogleVertexTTSProvider
            return GoogleVertexTTSProvider(output_dir=output_dir)
        except Exception:
            pass
    elif provider == "fake":
        return FakeTTSProvider(output_dir=output_dir)

    return EdgeTTSProvider(output_dir=output_dir)
