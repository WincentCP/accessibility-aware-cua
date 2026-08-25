"""Small OpenAI Speech API adapter for the accessible Indonesian voice guide."""

from __future__ import annotations

import httpx


INDONESIAN_GUIDE_INSTRUCTIONS = (
    "Speak entirely in natural Indonesian. Use a warm, cheerful, friendly, conversational "
    "tone, like a supportive Indonesian guide. Sound lively but calm, never stiff or robotic. "
    "Pronounce Indonesian words clearly at a moderate pace with short natural pauses. "
    "Do not translate the text into English."
)


class OpenAITTSClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini-tts",
        voice: str = "coral",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY belum dikonfigurasi.")
        self.model = model
        self.voice = voice
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            trust_env=False,
            transport=transport,
        )

    def generate(self, text: str) -> bytes:
        response = self.client.post(
            "/audio/speech",
            json={
                "model": self.model,
                "voice": self.voice,
                "input": text,
                "instructions": INDONESIAN_GUIDE_INSTRUCTIONS,
                "response_format": "mp3",
            },
        )
        if not response.is_success:
            raise RuntimeError(f"OpenAI Speech API {response.status_code}: {response.text[:500]}")
        return response.content

    def close(self) -> None:
        self.client.close()
