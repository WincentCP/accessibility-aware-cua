"""Gemini structured-output adapter for the existing planner contract."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from packages.agent.planner import ModelResponse


TRANSIENT_GEMINI_STATUS_CODES = {429, 500, 502, 503, 504}


class GeminiStructuredClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-3.7-flash",
        fallback_model: str | None = "gemini-3.6-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        max_output_tokens: int = 1_200,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY belum dikonfigurasi.")
        if max_retries < 0:
            raise ValueError("max_retries tidak boleh negatif.")
        self.model = model
        self.fallback_model = fallback_model.strip() if fallback_model else None
        self.max_output_tokens = max_output_tokens
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
    def _output_text(payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini tidak mengembalikan kandidat jawaban.")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        for part in parts:
            if part.get("text"):
                return str(part["text"])
        raise RuntimeError("Gemini tidak mengembalikan structured output text.")

    def _request_body(self, *, prompt: str, schema: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        return {
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
        }

    def generate(self, *, prompt: str, schema: dict[str, Any], request: dict[str, Any]) -> ModelResponse:
        started = time.perf_counter()
        body = self._request_body(prompt=prompt, schema=schema, request=request)
        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)

        last_error = "Gemini request gagal tanpa detail."
        for model_index, model in enumerate(models):
            for attempt in range(self.max_retries + 1):
                try:
                    response = self.client.post(
                        f"/models/{model}:generateContent",
                        json=body,
                    )
                except httpx.TransportError as exc:
                    last_error = f"Gemini transport error pada {model}: {exc}"
                    if attempt < self.max_retries:
                        time.sleep(self.retry_base_seconds * (2**attempt))
                        continue
                    break

                if response.is_success:
                    payload = response.json()
                    usage = payload.get("usageMetadata") or {}
                    return ModelResponse(
                        payload=json.loads(self._output_text(payload)),
                        input_tokens=int(usage.get("promptTokenCount", 0)),
                        output_tokens=int(usage.get("candidatesTokenCount", 0)),
                        model_id=str(payload.get("modelVersion") or model),
                        provider="google-gemini",
                        latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
                    )

                last_error = f"Gemini API {response.status_code} pada {model}: {response.text[:500]}"
                if response.status_code not in TRANSIENT_GEMINI_STATUS_CODES:
                    raise RuntimeError(last_error)
                if attempt < self.max_retries:
                    time.sleep(self.retry_base_seconds * (2**attempt))
                    continue
                break

            # Pindah ke fallback hanya setelah primary gagal karena error sementara/transport.
            if model_index < len(models) - 1:
                continue

        raise RuntimeError(
            f"{last_error} Primary dan fallback Gemini tidak tersedia setelah retry."
        )

    def close(self) -> None:
        self.client.close()
