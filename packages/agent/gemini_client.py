"""Gemini structured-output adapter for the existing planner contract."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from packages.agent.planner import ModelResponse


class GeminiStructuredClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        max_output_tokens: int = 1_200,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY belum dikonfigurasi.")
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"x-goog-api-key": api_key},
            timeout=timeout_seconds,
            trust_env=False,
            transport=transport,
        )

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini tidak mengembalikan kandidat jawaban.")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        for part in parts:
            if part.get("text"):
                return str(part["text"])
        raise RuntimeError("Gemini tidak mengembalikan structured output text.")

    def generate(self, *, prompt: str, schema: dict[str, Any], request: dict[str, Any]) -> ModelResponse:
        started = time.perf_counter()
        response = self.client.post(
            f"/models/{self.model}:generateContent",
            json={
                "systemInstruction": {"parts": [{"text": prompt}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": json.dumps(request, ensure_ascii=False, sort_keys=True)}
                        ],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                    "maxOutputTokens": self.max_output_tokens,
                    "temperature": 0,
                },
            },
        )
        if not response.is_success:
            raise RuntimeError(f"Gemini API {response.status_code}: {response.text[:500]}")
        payload = response.json()
        usage = payload.get("usageMetadata") or {}
        return ModelResponse(
            payload=json.loads(self._output_text(payload)),
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            model_id=str(payload.get("modelVersion") or self.model),
            provider="google-gemini",
            latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
        )

    def close(self) -> None:
        self.client.close()
