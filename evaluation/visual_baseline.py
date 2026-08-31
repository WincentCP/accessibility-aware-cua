"""Screenshot-only B0 baseline.

This module intentionally has no accessibility-tree, DOM-role, semantic-ref,
task-map, hidden-oracle, or recovery dependency. Final scoring happens in the
outer evaluator after the visual agent stops.
"""

from __future__ import annotations

import hashlib
import json
import time
from enum import StrEnum
from typing import Any

import httpx
from pydantic import Field, ValidationError, model_validator

from evaluation.contracts import ExecutionOutcome
from packages.agent.contracts import ClosedModel

VISUAL_PROMPT_VERSION = "visual-baseline-v1"
VISUAL_PROMPT = """You are the visual-only B0 browser baseline in a controlled synthetic website.
Use only the supplied screenshot and viewport. Never assume DOM, accessibility-tree, selectors,
element roles, hidden state, or target coordinates that are not visually grounded. Perform one
bounded action at a time. Respect forbidden actions and stop at the stated completion boundary.
For form controls, click/type with pixel coordinates, use keyboard keys after focusing them, or
scroll when the target is outside the viewport.
Return done only when the visible page supports completion. Return JSON matching the schema."""
VISUAL_PROMPT_HASH = hashlib.sha256(VISUAL_PROMPT.encode("utf-8")).hexdigest()


class VisualInfrastructureError(RuntimeError):
    """Browser/model transport failed independently of agent capability."""


class VisualPlanningError(RuntimeError):
    """The visual planner returned an unusable decision."""


class VisualActionType(StrEnum):
    CLICK = "click"
    TYPE = "type"
    PRESS = "press"
    WAIT = "wait"
    SCROLL = "scroll"
    DONE = "done"


class VisualDecision(ClosedModel):
    action_type: VisualActionType
    x: int | None = Field(default=None, ge=0, le=10_000)
    y: int | None = Field(default=None, ge=0, le=10_000)
    input_value: str | None = Field(default=None, max_length=4_000)
    key: str | None = Field(default=None, max_length=64)
    wait_ms: int | None = Field(default=None, ge=100, le=3_000)
    scroll_delta_y: int | None = Field(default=None, ge=-1_000, le=1_000)
    expected_visual_effect: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def action_shape(self) -> VisualDecision:
        if self.action_type in {VisualActionType.CLICK, VisualActionType.TYPE} and (
            self.x is None or self.y is None
        ):
            raise ValueError("Aksi visual click/type memerlukan x dan y.")
        if self.action_type is VisualActionType.TYPE and self.input_value is None:
            raise ValueError("Aksi visual type memerlukan input_value.")
        if self.action_type is VisualActionType.PRESS and not self.key:
            raise ValueError("Aksi visual press memerlukan key.")
        if self.action_type is VisualActionType.WAIT and self.wait_ms is None:
            raise ValueError("Aksi visual wait memerlukan wait_ms.")
        if self.action_type is VisualActionType.SCROLL and (
            self.scroll_delta_y is None or self.scroll_delta_y == 0
        ):
            raise ValueError("Aksi visual scroll memerlukan scroll_delta_y non-zero.")
        return self


class Screenshot(ClosedModel):
    image_base64: str = Field(min_length=16)
    mime_type: str = Field(pattern=r"^image/jpeg$")
    width: int = Field(gt=0, le=10_000)
    height: int = Field(gt=0, le=10_000)
    url: str = Field(min_length=1, max_length=4_000)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.image_base64.encode("ascii")).hexdigest()


class VisualBridge:
    def __init__(
        self,
        bridge_url: str,
        app_secret: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client = httpx.Client(
            base_url=bridge_url.rstrip("/"),
            headers={"Authorization": f"Bearer {app_secret}"},
            timeout=10.0,
            trust_env=False,
            transport=transport,
        )

    def screenshot(self) -> Screenshot:
        response = self.client.get("/page/screenshot")
        response.raise_for_status()
        return Screenshot.model_validate(response.json())

    def act(self, decision: VisualDecision) -> None:
        payload: dict[str, Any]
        if decision.action_type is VisualActionType.CLICK:
            payload = {"op": "coordinate_click", "x": decision.x, "y": decision.y}
        elif decision.action_type is VisualActionType.TYPE:
            payload = {
                "op": "coordinate_type",
                "x": decision.x,
                "y": decision.y,
                "value": decision.input_value,
            }
        elif decision.action_type is VisualActionType.PRESS:
            payload = {"op": "keyboard_press", "key": decision.key}
        elif decision.action_type is VisualActionType.WAIT:
            payload = {"op": "wait", "duration_ms": decision.wait_ms}
        elif decision.action_type is VisualActionType.SCROLL:
            payload = {"op": "coordinate_scroll", "delta_y": decision.scroll_delta_y}
        else:
            raise ValueError("DONE tidak boleh dikirim sebagai browser action.")
        response = self.client.post("/page/action", json=payload)
        response.raise_for_status()

    def close(self) -> None:
        self.client.close()


class GeminiVisualClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        fallback_model: str | None,
        max_retries: int,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY belum dikonfigurasi untuk B0.")
        self.models = [model, *([fallback_model] if fallback_model and fallback_model != model else [])]
        self.max_retries = max_retries
        self.last_model_id: str | None = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"x-goog-api-key": api_key},
            timeout=60.0,
            trust_env=False,
            transport=transport,
        )

    def decide(self, request: dict[str, Any], screenshot: Screenshot) -> VisualDecision:
        schema = VisualDecision.model_json_schema()
        correction: dict[str, Any] | None = None
        for schema_attempt in range(2):
            body_request = dict(request)
            if correction:
                body_request["schema_correction"] = correction
            body = {
                "systemInstruction": {"parts": [{"text": VISUAL_PROMPT}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": json.dumps(body_request, ensure_ascii=False, sort_keys=True)},
                            {
                                "inlineData": {
                                    "mimeType": screenshot.mime_type,
                                    "data": screenshot.image_base64,
                                }
                            },
                        ],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                    "maxOutputTokens": 1_200,
                    "temperature": 0,
                },
            }
            payload = self._generate(body)
            try:
                return VisualDecision.model_validate_json(self._text(payload))
            except (ValidationError, ValueError) as exc:
                if schema_attempt == 1:
                    raise VisualPlanningError(
                        "B0 menghasilkan action schema invalid setelah satu retry."
                    ) from exc
                correction = {"instruction": "Return only valid JSON matching the schema."}
        raise AssertionError("unreachable")

    def _generate(self, body: dict[str, Any]) -> dict[str, Any]:
        last_error = "Gemini visual request gagal."
        for model in self.models:
            for attempt in range(self.max_retries + 1):
                try:
                    response = self.client.post(f"/models/{model}:generateContent", json=body)
                except httpx.TransportError as exc:
                    last_error = f"Gemini visual transport error: {exc}"
                    if attempt < self.max_retries:
                        time.sleep(2**attempt)
                        continue
                    break
                if response.is_success:
                    payload = response.json()
                    self.last_model_id = str(payload.get("modelVersion") or model)
                    usage = payload.get("usageMetadata") or {}
                    self.total_input_tokens += int(usage.get("promptTokenCount", 0))
                    self.total_output_tokens += int(usage.get("candidatesTokenCount", 0))
                    return payload
                last_error = f"Gemini visual API {response.status_code}: {response.text[:500]}"
                if response.status_code not in {429, 500, 502, 503, 504}:
                    raise VisualInfrastructureError(last_error)
                if attempt < self.max_retries:
                    time.sleep(2**attempt)
            # Try fallback after the primary exhausts transient retries.
        raise VisualInfrastructureError(last_error)

    @staticmethod
    def _text(payload: dict[str, Any]) -> str:
        for candidate in payload.get("candidates") or []:
            for part in ((candidate.get("content") or {}).get("parts") or []):
                if part.get("text"):
                    return str(part["text"])
        raise VisualPlanningError("Gemini visual tidak mengembalikan structured output.")

    def close(self) -> None:
        self.client.close()


class VisualBaselineRunner:
    def __init__(self, *, bridge: VisualBridge, model: GeminiVisualClient) -> None:
        self.bridge = bridge
        self.model = model

    def _metadata(self) -> dict[str, Any]:
        return {
            "model_id": getattr(self.model, "last_model_id", None),
            "prompt_version": VISUAL_PROMPT_VERSION,
            "prompt_hash": VISUAL_PROMPT_HASH,
            "input_tokens": int(getattr(self.model, "total_input_tokens", 0)),
            "output_tokens": int(getattr(self.model, "total_output_tokens", 0)),
        }

    def run(
        self,
        *,
        goal: str,
        forbidden_actions: list[str],
        completion_boundary: str,
        max_steps: int,
        token_budget: int = 20_000,
    ) -> ExecutionOutcome:
        started = time.perf_counter()
        effects: list[str] = []
        for step_index in range(max_steps):
            before = self.bridge.screenshot()
            try:
                decision = self.model.decide(
                    {
                        "goal": goal,
                        "forbidden_actions": forbidden_actions,
                        "completion_boundary": completion_boundary,
                        "viewport": {"width": before.width, "height": before.height},
                        "verified_visual_effects": effects,
                        "remaining_steps": max_steps - step_index,
                        "remaining_tokens": max(
                            0,
                            token_budget
                            - int(getattr(self.model, "total_input_tokens", 0))
                            - int(getattr(self.model, "total_output_tokens", 0)),
                        ),
                    },
                    before,
                )
            except VisualPlanningError as exc:
                return ExecutionOutcome(
                    terminal_reason="ERROR",
                    error_code="INVALID_ACTION",
                    step_count=step_index,
                    duration_ms=round((time.perf_counter() - started) * 1_000),
                    infrastructure_error=None,
                    agent_claimed_success=False,
                    final_state=None,
                    oracle_result=None,
                    runtime_metadata=self._metadata(),
                ).model_copy(update={"error_code": str(exc)[:80]})
            used_tokens = int(getattr(self.model, "total_input_tokens", 0)) + int(
                getattr(self.model, "total_output_tokens", 0)
            )
            if used_tokens > token_budget:
                return ExecutionOutcome(
                    terminal_reason="ERROR",
                    error_code="TOKEN_BUDGET_EXCEEDED",
                    step_count=step_index,
                    duration_ms=round((time.perf_counter() - started) * 1_000),
                    runtime_metadata=self._metadata(),
                )
            if decision.action_type is VisualActionType.DONE:
                return ExecutionOutcome(
                    agent_claimed_success=True,
                    terminal_reason="COMPLETED",
                    step_count=step_index,
                    duration_ms=round((time.perf_counter() - started) * 1_000),
                    runtime_metadata=self._metadata(),
                )
            try:
                self.bridge.act(decision)
                after = self.bridge.screenshot()
            except httpx.TransportError:
                # Bridge/network availability is an infrastructure failure, not
                # evidence that the visual agent chose an invalid action.
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    raise
                return ExecutionOutcome(
                    terminal_reason="ERROR",
                    error_code=type(exc).__name__,
                    step_count=step_index + 1,
                    duration_ms=round((time.perf_counter() - started) * 1_000),
                    runtime_metadata=self._metadata(),
                )
            except ValueError as exc:
                return ExecutionOutcome(
                    terminal_reason="ERROR",
                    error_code=type(exc).__name__,
                    step_count=step_index + 1,
                    duration_ms=round((time.perf_counter() - started) * 1_000),
                    runtime_metadata=self._metadata(),
                )
            if decision.action_type is not VisualActionType.WAIT and before.digest == after.digest:
                return ExecutionOutcome(
                    terminal_reason="ERROR",
                    error_code="VISUAL_VERIFICATION_FAILED",
                    step_count=step_index + 1,
                    duration_ms=round((time.perf_counter() - started) * 1_000),
                    runtime_metadata=self._metadata(),
                )
            effects.append(decision.expected_visual_effect)
        return ExecutionOutcome(
            terminal_reason="MAX_STEPS",
            error_code="MAX_STEPS_REACHED",
            step_count=max_steps,
            duration_ms=round((time.perf_counter() - started) * 1_000),
            runtime_metadata=self._metadata(),
        )
