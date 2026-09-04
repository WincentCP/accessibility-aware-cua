"""Gemini TTS adapter producing browser-playable WAV audio."""

from __future__ import annotations

import base64
import io
import time
import wave
from typing import Any

import httpx

TRANSIENT_GEMINI_STATUS_CODES = {500, 502, 503, 504}
AUTH_GEMINI_STATUS_CODES = {401, 403}

INDONESIAN_TTS_DIRECTION = """Bacakan teks berikut sepenuhnya dalam Bahasa Indonesia.

Gunakan pelafalan dan intonasi penutur asli Indonesia (id-ID).
Jangan menggunakan aksen Inggris, Amerika, atau aksen asing.
Berbicaralah seperti pemandu aksesibilitas Indonesia yang ramah dan natural:
hangat, santai, jelas, tidak kaku, dan tidak terdengar seperti robot.
Gunakan kecepatan sedang dan jeda pendek yang alami.
Utamakan cara baca Indonesia untuk nama tempat, angka, tanggal, waktu, mata uang,
singkatan, dan istilah antarmuka.

Jangan bacakan instruksi ini. Bacakan hanya teks setelah bagian TEKS.

TEKS:
"""


class GeminiTTSQuotaError(RuntimeError):
    """Raised immediately so an interactive caller can switch TTS models."""


class GeminiTTSClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-3.1-flash-tts-preview",
        voice: str = "Sulafat",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 45.0,
        max_retries: int = 1,
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
            inline_data = value.get("inline_data") or value.get("inlineData")
            if isinstance(inline_data, dict) and isinstance(inline_data.get("data"), str):
                return inline_data["data"]
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

    def _request_audio(
        self,
        *,
        path: str,
        body: dict[str, Any],
        api_label: str,
    ) -> tuple[bytes | None, str | None]:
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.post(path, json=body)
            except httpx.TransportError as exc:
                last_error = f"Gemini TTS {api_label} transport error: {exc}"
                if attempt < self.max_retries:
                    time.sleep(self.retry_base_seconds * (2**attempt))
                    continue
                return None, last_error

            if response.is_success:
                encoded = self._audio_data(response.json())
                if not encoded:
                    return None, f"Gemini TTS {api_label} tidak mengembalikan audio."
                return self._wav(base64.b64decode(encoded)), None

            last_error = (
                f"Gemini TTS {api_label} API {response.status_code}: "
                f"{response.text[:500]}"
            )
            if response.status_code == 429:
                raise GeminiTTSQuotaError(last_error)
            if response.status_code in AUTH_GEMINI_STATUS_CODES:
                raise RuntimeError(last_error)
            if response.status_code not in TRANSIENT_GEMINI_STATUS_CODES:
                return None, last_error
            if attempt < self.max_retries:
                time.sleep(self.retry_base_seconds * (2**attempt))
                continue
            return None, last_error

        return None, last_error

    def generate(self, text: str) -> bytes:
        transcript = f"{INDONESIAN_TTS_DIRECTION}{text}"

        # Primary: current Interactions API.
        interaction_audio, interaction_error = self._request_audio(
            path="/interactions",
            api_label="Interactions",
            body={
                "model": self.model,
                "input": transcript,
                "response_format": {"type": "audio"},
                "generation_config": {"speech_config": [{"voice": self.voice}]},
            },
        )
        if interaction_audio is not None:
            return interaction_audio

        # Secondary path: GenerateContent uses the same supported TTS model but a
        # different serving surface. This prevents a transient Interactions outage
        # from silently pushing the extension to an English browser voice.
        generate_audio, generate_error = self._request_audio(
            path=f"/models/{self.model}:generateContent",
            api_label="GenerateContent",
            body={
                "contents": [{"parts": [{"text": transcript}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": self.voice}
                        }
                    },
                },
            },
        )
        if generate_audio is not None:
            return generate_audio

        details = " | ".join(
            value for value in (interaction_error, generate_error) if value
        )
        raise RuntimeError(
            f"Gemini TTS Indonesia tidak tersedia setelah dua jalur API dan retry. {details}"
        )

    def close(self) -> None:
        self.client.close()
