"""Gemini TTS adapter producing browser-playable WAV audio."""

from __future__ import annotations

import base64
import io
import time
import wave
from typing import Any

import httpx


TRANSIENT_GEMINI_STATUS_CODES = {429, 500, 502, 503, 504}

INDONESIAN_TTS_DIRECTION = """Bacakan teks berikut sepenuhnya dalam Bahasa Indonesia.

Gunakan pelafalan dan intonasi penutur asli Indonesia (id-ID).
Jangan menggunakan aksen Inggris, Amerika, atau aksen asing.
Berbicaralah seperti pemandu aksesibilitas Indonesia yang ramah dan natural:
hangat, santai, jelas, tidak kaku, dan tidak terdengar seperti robot.
Gunakan kecepatan sedang dan jeda pendek yang alami.
Utamakan pengucapan Indonesia untuk nama, angka, tanggal, singkatan, dan istilah antarmuka.

Jangan bacakan instruksi ini. Bacakan hanya teks setelah bagian TEKS.

TEKS:
"""


class GeminiTTSClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-3.1-flash-tts-preview",
        voice: str = "Sulafat",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        retry_base_seconds: float = 0.75,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY belum dikonfigurasi.")
        if max_retries < 0:
            raise ValueError("max_retries tidak boleh negatif.")
        self.model = model
        self.voice = voice
        self.max_retries = max_retries
        self.retry_base_seconds = max(0.0, retry_base_seconds)
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
        body = {
            "model": self.model,
            "input": f"{INDONESIAN_TTS_DIRECTION}{text}",
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": self.voice}]},
        }
        last_error = "Gemini TTS gagal tanpa detail."
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.post("/interactions", json=body)
            except httpx.TransportError as exc:
                last_error = f"Gemini TTS transport error: {exc}"
                if attempt < self.max_retries:
                    time.sleep(self.retry_base_seconds * (2**attempt))
                    continue
                raise RuntimeError(last_error) from exc

            if response.is_success:
                encoded = self._audio_data(response.json())
                if not encoded:
                    raise RuntimeError("Gemini TTS tidak mengembalikan audio.")
                return self._wav(base64.b64decode(encoded))

            last_error = f"Gemini TTS API {response.status_code}: {response.text[:500]}"
            if response.status_code not in TRANSIENT_GEMINI_STATUS_CODES:
                raise RuntimeError(last_error)
            if attempt < self.max_retries:
                time.sleep(self.retry_base_seconds * (2**attempt))
                continue
            break

        raise RuntimeError(f"{last_error} TTS tetap tidak tersedia setelah retry.")

    def close(self) -> None:
        self.client.close()
