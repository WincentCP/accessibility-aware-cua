from __future__ import annotations

import json

import httpx

from backend.agent.gemini_client import GeminiStructuredClient
from backend.agent.gemini_tts import GeminiTTSClient


def test_gemini_planner_retries_503_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return httpx.Response(
            200,
            json={
                "modelVersion": "primary-model",
                "candidates": [{"content": {"parts": [{"text": '{"choice":"observe"}'}]}}],
                "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1},
            },
        )

    client = GeminiStructuredClient(
        "key",
        model="primary-model",
        fallback_model="fallback-model",
        max_retries=1,
        retry_base_seconds=0,
        base_url="https://unit.test/v1beta",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.generate(
            prompt="Return JSON.",
            schema={"type": "object", "properties": {"choice": {"type": "string"}}},
            request={"goal": "observe"},
        )
    finally:
        client.close()

    assert calls == 2
    assert result.payload == {"choice": "observe"}
    assert result.model_id == "primary-model"


def test_gemini_planner_falls_back_after_primary_stays_overloaded() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if "primary-model" in request.url.path:
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return httpx.Response(
            200,
            json={
                "modelVersion": "fallback-model",
                "candidates": [{"content": {"parts": [{"text": '{"choice":"observe"}'}]}}],
                "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1},
            },
        )

    client = GeminiStructuredClient(
        "key",
        model="primary-model",
        fallback_model="fallback-model",
        max_retries=1,
        retry_base_seconds=0,
        base_url="https://unit.test/v1beta",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.generate(
            prompt="Return JSON.",
            schema={"type": "object", "properties": {"choice": {"type": "string"}}},
            request={"goal": "observe"},
        )
    finally:
        client.close()

    assert paths == [
        "/v1beta/models/primary-model:generateContent",
        "/v1beta/models/primary-model:generateContent",
        "/v1beta/models/fallback-model:generateContent",
    ]
    assert result.model_id == "fallback-model"


def test_gemini_tts_retries_transient_failure() -> None:
    calls = 0
    pcm = b"\x00\x00\x01\x00"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        assert payload["generation_config"]["speech_config"] == [{"voice": "Sulafat"}]
        if calls == 1:
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return httpx.Response(
            200,
            json={"output_audio": {"data": __import__("base64").b64encode(pcm).decode()}},
        )

    client = GeminiTTSClient(
        "key",
        model="tts-model",
        voice="Sulafat",
        max_retries=1,
        retry_base_seconds=0,
        base_url="https://unit.test/v1beta",
        transport=httpx.MockTransport(handler),
    )
    try:
        audio = client.generate("Halo, tugas siap.")
    finally:
        client.close()

    assert calls == 2
    assert audio.startswith(b"RIFF")
