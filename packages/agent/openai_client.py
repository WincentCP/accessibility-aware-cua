"""OpenAI Responses API adapter for the existing structured planner contract."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any

import httpx

from packages.agent.planner import ModelResponse


class OpenAIResponsesClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        max_output_tokens: int = 1_200,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY belum dikonfigurasi.")
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            trust_env=False,
            transport=transport,
        )

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return str(content["text"])
                if content.get("type") == "refusal":
                    raise RuntimeError(f"Planner model menolak request: {content.get('refusal', 'refusal')}")
        raise RuntimeError("Responses API tidak mengembalikan structured output text.")

    @staticmethod
    def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
        """Convert Pydantic JSON Schema to the strict Responses API subset."""

        normalized = deepcopy(schema)

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                value.pop("default", None)
                properties = value.get("properties")
                if value.get("type") == "object" and isinstance(properties, dict):
                    value["additionalProperties"] = False
                    value["required"] = list(properties)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(normalized)
        return normalized

    def generate(self, *, prompt: str, schema: dict[str, Any], request: dict[str, Any]) -> ModelResponse:
        started = time.perf_counter()
        response = self.client.post(
            "/responses",
            json={
                "model": self.model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": json.dumps(request, ensure_ascii=False, sort_keys=True),
                            }
                        ],
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "planner_decision",
                        "schema": self._strict_schema(schema),
                        "strict": True,
                    }
                },
                "max_output_tokens": self.max_output_tokens,
            },
        )
        if not response.is_success:
            raise RuntimeError(f"OpenAI Responses API {response.status_code}: {response.text[:500]}")
        payload = response.json()
        usage = payload.get("usage") or {}
        return ModelResponse(
            payload=json.loads(self._output_text(payload)),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            model_id=str(payload.get("model") or self.model),
            provider="openai-responses",
            latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
        )

    def close(self) -> None:
        self.client.close()
