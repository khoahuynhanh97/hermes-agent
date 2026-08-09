"""Google Vertex Gemini TTS provider adapter.

Implements TextToSpeechPort against the Gemini TTS generateContent API.
Reuses ADC auth from providers/vertex_auth.py. No credentials in code.

Contract:
- TTS_PROVIDER=google_vertex
- TTS_MODEL=gemini-3.1-flash-tts-preview
- GOOGLE_CLOUD_LOCATION=global
- GOOGLE_CLOUD_PROJECT=gen-lang-client-0816609628
"""

from __future__ import annotations

import base64
import os
import wave
from pathlib import Path

import requests

from hermes.ports.text_to_speech import TextToSpeechPort, TTSRequest, TTSResult
from providers.vertex_auth import get_access_token, vertex_model_endpoint, vertex_required_project


def _tts_endpoint(project: str, location: str, model: str) -> str:
    return (
        f"https://aiplatform.googleapis.com/v1beta1/projects/{project}"
        f"/locations/{location}/publishers/google/models/{model}:generateContent"
    )


class GoogleVertexTTSProvider(TextToSpeechPort):
    def __init__(self, project: str | None = None, location: str | None = None,
                 model: str | None = None, output_dir: str | None = None, timeout: int = 90):
        self.project = project or vertex_required_project()

        if os.environ.get("TTS_PROVIDER", "").strip().lower() == "fake" and \
           os.environ.get("HERMES_ALLOW_FAKE_PROVIDERS", "").strip() != "1":
            raise ValueError(
                "TTS_PROVIDER=fake selected but HERMES_ALLOW_FAKE_PROVIDERS is not set"
            )
        self.location = (location or os.environ.get("GOOGLE_CLOUD_LOCATION", "")).strip() or "global"
        self.model = (model or os.environ.get("TTS_MODEL", "")).strip() or "gemini-3.1-flash-tts-preview"
        self.timeout = int(timeout)

        configured = output_dir or os.environ.get("HERMES_TTS_OUTPUT_DIR", "")
        self.output_dir = Path(configured).expanduser().resolve() if configured else (Path.cwd() / "audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # TextToSpeechPort
    # ------------------------------------------------------------------

    def synthesize(self, request: TTSRequest) -> TTSResult:
        try:
            token = get_access_token()
            payload = {
                "contents": [{"role": "user", "parts": [{"text": self._build_text(request)}]}],
                "generationConfig": {
                    "speechConfig": {
                        "languageCode": request.language,
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": request.voice}
                        },
                    }
                },
            }

            endpoint = _tts_endpoint(self.project, self.location, self.model)
            response = requests.post(
                endpoint, headers={"Authorization": f"Bearer {token}"},
                json=payload, timeout=self.timeout,
            )
            if response.status_code != 200:
                return TTSResult(
                    request_id=request.request_id, success=False,
                    error_message=self._normalize_error(response),
                )

            audio = self._extract_audio(response.json())
            if not audio:
                return TTSResult(
                    request_id=request.request_id, success=False,
                    error_message="vertex tts returned no audio data",
                )

            mime, data = audio
            safe = "".join(c for c in request.request_id if c.isalnum() or c in "-_.") or "voiceover"
            wav_path = self.output_dir / f"{safe}.wav"
            self._write_wav(mime, data, wav_path)

            return TTSResult(
                request_id=request.request_id, success=True, wav_path=str(wav_path),
                provider="google_vertex", model=self.model, voice=request.voice,
            )
        except Exception as error:  # noqa: BLE001
            return TTSResult(request_id=request.request_id, success=False, error_message=str(error))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _build_text(request: TTSRequest) -> str:
        """Combine style_prompt + voiceover text into the single contents text.

        Pure mapping; no creative defaults here. When style_prompt is empty a
        minimal narration instruction plus the text is sent.
        """
        text = (request.text or "").strip()
        style = (request.style_prompt or "").strip()
        if style:
            return f"{style}\n\nSay the following:\n{text}"
        return f"Say the following:\n{text}"

    def _extract_audio(self, body: dict) -> tuple[str, bytes] | None:
        for candidate in body.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    mime = inline.get("mimeType") or inline.get("mime_type") or "audio/pcm"
                    try:
                        return mime, base64.b64decode(inline["data"])
                    except Exception:
                        return None
        return None

    def _write_wav(self, mime: str, data: bytes, path: Path) -> None:
        """Write 24kHz/16-bit/mono WAV from PCM bytes, or copy directly if already WAV."""
        if "wav" in mime:
            path.write_bytes(data)
            return
        # assume raw PCM (audio/pcm;rate=24000, 16-bit mono)
        sample_rate = 24000
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(data)

    @staticmethod
    def _normalize_error(response: requests.Response) -> str:
        try:
            message = response.json().get("error", {}).get("message", "")
            return f"vertex http {response.status_code}: {message}" if message else f"vertex http {response.status_code}"
        except ValueError:
            return f"vertex http {response.status_code}"