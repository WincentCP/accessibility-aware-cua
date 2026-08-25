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
from packages.agent.openai_client import OpenAIResponsesClient
from packages.agent.openai_tts import INDONESIAN_GUIDE_INSTRUCTIONS, OpenAITTSClient
from packages.agent.planner import PlannerDecision
from packages.agent.remote_page import RemoteBridgeError, RemotePage


def test_openai_adapter_uses_strict_responses_structured_output() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"choice":"observe"}'}
                        ],
                    }
                ],
                "usage": {"input_tokens": 12, "output_tokens": 4},
            },
        )

    client = OpenAIResponsesClient(
        "test-key",
        model="test-model",
        base_url="https://unit.test/v1",
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
    assert result.input_tokens == 12
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    assert captured["input"][1]["content"][0]["type"] == "input_text"


def test_openai_adapter_normalizes_pydantic_schema_for_strict_outputs() -> None:
    schema = OpenAIResponsesClient._strict_schema(PlannerDecision.model_json_schema())

    def assert_strict(value: object) -> None:
        if isinstance(value, dict):
            assert "default" not in value
            properties = value.get("properties")
            if value.get("type") == "object" and isinstance(properties, dict):
                assert value["additionalProperties"] is False
                assert value["required"] == list(properties)
            for child in value.values():
                assert_strict(child)
        elif isinstance(value, list):
            for child in value:
                assert_strict(child)

    assert_strict(schema)
    action = schema["$defs"]["AgentAction"]
    assert "schema_version" in action["required"]
    assert "target_ref" in action["required"]
    assert "requires_approval" in action["required"]


def test_openai_tts_requests_cheerful_indonesian_audio() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, content=b"fake-mp3")

    client = OpenAITTSClient(
        "test-key",
        model="test-tts",
        voice="coral",
        base_url="https://unit.test/v1",
        transport=httpx.MockTransport(handler),
    )
    try:
        audio = client.generate("Tugas siap. Silakan mulai.")
    finally:
        client.close()

    assert audio == b"fake-mp3"
    assert captured == {
        "model": "test-tts",
        "voice": "coral",
        "input": "Tugas siap. Silakan mulai.",
        "instructions": INDONESIAN_GUIDE_INSTRUCTIONS,
        "response_format": "mp3",
    }


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
        openai_api_key=api_key,
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
    assert response.json()["detail"] == "OPENAI_API_KEY belum diisi di .env lokal."


def test_voice_api_fails_closed_when_key_is_missing() -> None:
    app = create_app(_settings(api_key=None))
    with TestClient(app) as client:
        response = client.post("/api/voice/speech", json={"text": "Halo!"})
    assert response.status_code == 503
    assert response.json()["detail"] == "OPENAI_API_KEY belum diisi di .env lokal."


def test_live_request_accepts_automatic_public_benchmark_goal() -> None:
    app = create_app(_settings(api_key=None))
    reset = app.state.case_store.reset("T01", "C0", 456)
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/runs",
            json={"benchmark_session_id": reset["session_id"]},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "OPENAI_API_KEY belum diisi di .env lokal."


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
