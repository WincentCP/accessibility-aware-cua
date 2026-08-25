"""Gemini TTS adapter producing browser-playable WAV audio."""

from __future__ import annotations

import base64
import io
import wave
from typing import Any

import httpx


INDONESIAN_TTS_DIRECTION = """Synthesize speech for the transcript below.
Audio profile: a friendly Indonesian accessibility guide.
Director's notes: speak entirely in natural Indonesian with a warm, upbeat, cheerful
conversational tone. Sound lively but calm, never stiff or robotic. Use clear articulation,
a moderate pace, and short natural pauses. Read only the transcript, not these directions.

TRANSCRIPT:
"""


class GeminiTTSClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash-preview-tts",
        voice: str = "Puck",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY belum dikonfigurasi.")
        self.model = model
        self.voice = voice
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"x-goog-api-key": api_key},
            timeout=timeout_seconds,
            trust_env=False,
            transport=transport,
        )

    @staticmethod
    def _audio_data(value: Any) -> str | None:
        if isinstance(value, dict):
            output_audio = value.get("output_audio") or value.get("outputAudio")
            if isinstance(output_audio, dict) and isinstance(output_audio.get("data"), str):
                return output_audio["data"]
            if value.get("type") == "audio" and isinstance(value.get("data"), str):
                return value["data"]
            for child in value.values():
                result = GeminiTTSClient._audio_data(child)
                if result:
                    return result
        elif isinstance(value, list):
            for child in value:
                result = GeminiTTSClient._audio_data(child)
                if result:
                    return result
        return None

    @staticmethod
    def _wav(pcm: bytes) -> bytes:
        if pcm.startswith(b"RIFF"):
            return pcm
        target = io.BytesIO()
        with wave.open(target, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(24_000)
            writer.writeframes(pcm)
        return target.getvalue()

    def generate(self, text: str) -> bytes:
        response = self.client.post(
            "/interactions",
            json={
                "model": self.model,
                "input": f"{INDONESIAN_TTS_DIRECTION}{text}",
                "response_format": {"type": "audio"},
                "generation_config": {"speech_config": [{"voice": self.voice}]},
            },
        )
        if not response.is_success:
            raise RuntimeError(f"Gemini TTS API {response.status_code}: {response.text[:500]}")
        encoded = self._audio_data(response.json())
        if not encoded:
            raise RuntimeError("Gemini TTS tidak mengembalikan audio.")
        return self._wav(base64.b64decode(encoded))

    def close(self) -> None:
        self.client.close()
