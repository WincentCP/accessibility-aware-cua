"""Bounded single-agent structured planner and goal normalization."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field, ValidationError, model_validator

from backend.agent.contracts import ActionType, AgentAction, ClosedModel
from backend.agent.predicates import ExpectedPostcondition

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "planner_v1.txt"
PROMPT_VERSION = "planner-v1"


class NormalizedGoal(ClosedModel):
    objective: str = Field(min_length=1, max_length=4_000)
    constraints: list[str] = Field(default_factory=list, max_length=32)
    forbidden_actions: list[str] = Field(default_factory=list, max_length=32)
    completion_boundary: str = Field(min_length=1, max_length=2_000)
    material_ambiguities: list[str] = Field(default_factory=list, max_length=8)


def normalize_input(text: str) -> NormalizedGoal:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        raise ValueError("Tujuan pengguna tidak boleh kosong")
    sentences = [part.strip() for part in cleaned.replace(";", ".").split(".") if part.strip()]
    constraints = [
        part
        for part in sentences
        if any(token in part.casefold() for token in ("harus", "maksimal", "paling", "hanya"))
    ]
    forbidden = [
        part
        for part in sentences
        if any(token in part.casefold() for token in ("jangan", "tanpa ", "berhenti sebelum"))
    ]
    boundary = (
        forbidden[-1] if forbidden else "Berhenti setelah tujuan terverifikasi tanpa aksi komitmen tambahan."
    )
    ambiguities: list[str] = []
    if len(cleaned) < 8 or cleaned.casefold() in {"lanjut", "kerjakan ini", "pilihkan"}:
        ambiguities.append("Tujuan atau kriteria pilihan belum cukup spesifik.")
    return NormalizedGoal(
        objective=cleaned,
        constraints=constraints,
        forbidden_actions=forbidden,
        completion_boundary=boundary,
        material_ambiguities=ambiguities,
    )


def clarify_if_needed(goal: NormalizedGoal) -> str | None:
    if not goal.material_ambiguities:
        return None
    return "Mohon jelaskan hasil yang diinginkan atau kriteria pilihan yang paling penting."


def apply_user_correction(goal: NormalizedGoal, correction: str) -> NormalizedGoal:
    update = normalize_input(correction)
    marker = f"Koreksi pengguna: {update.objective}"
    return goal.model_copy(
        update={
            "objective": f"{goal.objective}. {marker}",
            "constraints": list(dict.fromkeys([*goal.constraints, marker, *update.constraints])),
            "forbidden_actions": list(dict.fromkeys([*goal.forbidden_actions, *update.forbidden_actions])),
            "completion_boundary": (
                update.completion_boundary if update.forbidden_actions else goal.completion_boundary
            ),
            "material_ambiguities": update.material_ambiguities,
        }
    )


class PlannerDecision(ClosedModel):
    action: AgentAction
    postconditions: list[ExpectedPostcondition] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=1, max_length=500)
    goal_complete_after_verification: bool = False

    @model_validator(mode="after")
    def postconditions_match_step(self) -> PlannerDecision:
        if self.action.action_type in {ActionType.ASK_USER, ActionType.HANDOFF, ActionType.STOP}:
            raise ValueError("Graph-only action tidak boleh keluar lewat browser planner")
        return self


class PlannerRequest(ClosedModel):
    compact_observation: str = Field(max_length=12_000)
    goal: NormalizedGoal
    verified_progress: list[str] = Field(default_factory=list, max_length=32)
    relevant_items: list[str] = Field(default_factory=list, max_length=32)
    remaining_steps: int = Field(ge=0, le=100)
    remaining_tokens: int = Field(ge=0)
    last_verification: dict[str, Any] | None = None


class ModelResponse(ClosedModel):
    payload: dict[str, Any]
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    model_id: str
    provider: str
    latency_ms: int = Field(ge=0)


class StructuredModelClient(Protocol):
    def generate(self, *, prompt: str, schema: dict[str, Any], request: dict[str, Any]) -> ModelResponse: ...


class PlannerConfig(ClosedModel):
    model_id: str = "structured-model-candidate"
    provider: str = "provider-adapter"
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_output_tokens: int = Field(default=1_200, ge=128, le=8_000)
    task_token_budget: int = Field(default=20_000, ge=1_000)
    max_schema_retries: int = Field(default=1, ge=0, le=1)


class PlannerTelemetry(ClosedModel):
    model_id: str
    provider: str
    prompt_version: str = PROMPT_VERSION
    prompt_hash: str
    generation_settings: dict[str, Any]
    input_tokens: int
    output_tokens: int
    response_latency_ms: int
    schema_attempts: int = Field(ge=1, le=2)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StructuredPlanner:
    def __init__(self, client: StructuredModelClient, config: PlannerConfig | None = None) -> None:
        self.client = client
        self.config = config or PlannerConfig()
        self.prompt = PROMPT_PATH.read_text(encoding="utf-8")
        self.prompt_hash = hashlib.sha256(self.prompt.encode()).hexdigest()

    def plan(self, request: PlannerRequest) -> tuple[PlannerDecision, PlannerTelemetry]:
        if request.remaining_steps <= 0:
            raise RuntimeError("step budget exhausted")
        if request.remaining_tokens <= 0:
            raise RuntimeError("token budget exhausted")
        schema = PlannerDecision.model_json_schema()
        attempt = 0
        total_input = total_output = total_latency = 0
        correction: dict[str, Any] | None = None
        while True:
            model_request = request.model_dump(mode="json")
            if correction is not None:
                model_request["schema_correction"] = correction
            response = self.client.generate(prompt=self.prompt, schema=schema, request=model_request)
            total_input += response.input_tokens
            total_output += response.output_tokens
            total_latency += response.latency_ms
            if total_input + total_output > request.remaining_tokens:
                raise RuntimeError("token budget exceeded")
            try:
                decision = PlannerDecision.model_validate(response.payload)
                break
            except ValidationError as exc:
                if attempt >= self.config.max_schema_retries:
                    raise RuntimeError("planner schema invalid after controlled retry") from exc
                correction = {
                    "instruction": "Return only valid schema",
                    "errors": exc.errors(include_input=False),
                }
                attempt += 1
        telemetry = PlannerTelemetry(
            model_id=response.model_id,
            provider=response.provider,
            prompt_hash=self.prompt_hash,
            generation_settings={
                "temperature": self.config.temperature,
                "max_output_tokens": self.config.max_output_tokens,
            },
            input_tokens=total_input,
            output_tokens=total_output,
            response_latency_ms=total_latency,
            schema_attempts=attempt + 1,
        )
        return decision, telemetry


def config_hash(config: PlannerConfig) -> str:
    return hashlib.sha256(json.dumps(config.model_dump(), sort_keys=True).encode()).hexdigest()
