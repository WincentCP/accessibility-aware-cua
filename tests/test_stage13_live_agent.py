from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("CUA_ENV", "test")
os.environ.setdefault("CUA_APP_SECRET", "test-secret")

from apps.api.a11y_api.app import create_app
from apps.api.a11y_api.config import Settings
from packages.agent.gemini_client import GeminiStructuredClient
from packages.agent.gemini_tts import INDONESIAN_TTS_DIRECTION, GeminiTTSClient
from packages.agent.remote_page import RemoteBridgeError, RemotePage


def test_gemini_adapter_uses_structured_json_output() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["x-goog-api-key"] == "gemini-key"
        assert request.url.path.endswith("/models/test-gemini:generateContent")
        return httpx.Response(
            200,
            json={
                "modelVersion": "test-gemini-001",
                "candidates": [{"content": {"parts": [{"text": '{"choice":"observe"}'}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 3},
            },
        )

    client = GeminiStructuredClient(
        "gemini-key",
        model="test-gemini",
        base_url="https://unit.test/v1beta",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.generate(
            prompt="Return one decision.",
            schema={"type": "object", "properties": {"choice": {"type": "string"}}},
            request={"goal": "observe"},
        )
    finally:
        client.close()

    assert result.payload == {"choice": "observe"}
    assert result.provider == "google-gemini"
    assert result.input_tokens == 10
    assert captured["generationConfig"]["responseMimeType"] == "application/json"
    assert captured["generationConfig"]["responseJsonSchema"]["type"] == "object"


def test_gemini_tts_returns_browser_playable_wav() -> None:
    captured: dict = {}
    pcm = b"\x00\x00\x01\x00"

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["x-goog-api-key"] == "gemini-key"
        return httpx.Response(
            200,
            json={"output_audio": {"data": __import__("base64").b64encode(pcm).decode()}},
        )

    client = GeminiTTSClient(
        "gemini-key",
        model="test-tts",
        voice="Puck",
        base_url="https://unit.test/v1beta",
        transport=httpx.MockTransport(handler),
    )
    try:
        audio = client.generate("Halo, tugas sudah siap.")
    finally:
        client.close()

    assert audio.startswith(b"RIFF")
    assert captured["model"] == "test-tts"
    assert captured["generation_config"]["speech_config"] == [{"voice": "Puck"}]
    assert captured["input"] == f"{INDONESIAN_TTS_DIRECTION}Halo, tugas sudah siap."


def test_remote_page_uses_bearer_token_and_semantic_actions_only() -> None:
    requests: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, payload))
        assert request.headers["authorization"] == "Bearer local-secret"
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ready"})
        if request.url.path == "/page/meta":
            return httpx.Response(200, json={"url": "http://127.0.0.1:8000/task", "title": "Task"})
        if request.url.path == "/page/locator":
            return httpx.Response(200, json={"count": 1, "visible": True, "enabled": True, "editable": False})
        if request.url.path == "/page/action":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404, json={"error": "NOT_FOUND"})

    page = RemotePage(
        "http://bridge.test",
        "local-secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        assert page.health()["status"] == "ready"
        assert page.url == "http://127.0.0.1:8000/task"
        button = page.get_by_role("button", name="Pilih rute", exact=True)
        assert button.count() == 1
        button.focus()
        button.press("Enter")
    finally:
        page.close()

    actions = [payload for _, path, payload in requests if path == "/page/action"]
    assert actions == [
        {"op": "focus", "role": "button", "name": "Pilih rute", "exact": True},
        {"op": "press", "role": "button", "name": "Pilih rute", "exact": True, "key": "Enter"},
    ]


def test_remote_page_surfaces_bridge_errors_without_retrying() -> None:
    page = RemotePage(
        "http://bridge.test",
        "local-secret",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": "UNAUTHORIZED"})
        ),
    )
    try:
        try:
            page.health()
        except RemoteBridgeError as exc:
            assert "401" in str(exc)
        else:
            raise AssertionError("Remote bridge failure must not be swallowed")
    finally:
        page.close()


def _settings(*, api_key: str | None) -> Settings:
    return Settings(
        environment="test",
        app_secret="test-secret",
        host="127.0.0.1",
        port=8000,
        require_postgres=False,
        database_url="postgresql://unused",
        browser_profile_dir=Path(".runtime/test"),
        browser_headless=True,
        gemini_api_key=api_key,
        planner_provider="gemini",
        planner_model="gemini-2.5-flash",
    )


def test_live_api_fails_closed_before_browser_when_key_is_missing() -> None:
    app = create_app(_settings(api_key=None))
    reset = app.state.case_store.reset("T01", "C0", 123)
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/runs",
            json={
                "benchmark_session_id": reset["session_id"],
                "goal": "Pilih rute yang memenuhi batasan lalu berhenti sebelum pemesanan.",
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "GEMINI_API_KEY belum diisi di .env lokal."


def test_voice_api_fails_closed_when_key_is_missing() -> None:
    app = create_app(_settings(api_key=None))
    with TestClient(app) as client:
        response = client.post("/api/voice/speech", json={"text": "Halo!"})
    assert response.status_code == 503
    assert response.json()["detail"] == "GEMINI_API_KEY belum diisi di .env lokal."


def test_live_request_accepts_automatic_public_benchmark_goal() -> None:
    app = create_app(_settings(api_key=None))
    reset = app.state.case_store.reset("T01", "C0", 456)
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/runs",
            json={"benchmark_session_id": reset["session_id"]},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "GEMINI_API_KEY belum diisi di .env lokal."


def test_live_api_rejects_unknown_session_before_starting_agent() -> None:
    app = create_app(_settings(api_key="test-key"))
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/runs",
            json={
                "benchmark_session_id": "missing-session-id-000000",
                "goal": "Pilih satu rute valid.",
            },
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Sesi benchmark tidak ditemukan."
