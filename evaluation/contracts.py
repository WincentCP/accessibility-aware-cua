"""Typed contracts for manifests, executor output, and scored results."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from evaluation.config import EvaluationConfiguration
from packages.agent.contracts import ClosedModel


class FailureClass(StrEnum):
    NONE = "NONE"
    AGENT = "AGENT"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class ManifestRun(ClosedModel):
    run_id: str = Field(min_length=1, max_length=120)
    split: str = Field(pattern=r"^(?:pilot|final)$")
    task_id: str = Field(pattern=r"^(?:T(?:0[1-9]|1[0-2])|P0[1-4])$")
    condition_id: str = Field(pattern=r"^C[0-2]$")
    repetition: int = Field(ge=0, le=100)
    configuration: EvaluationConfiguration
    order_position: int = Field(ge=1, le=3)
    pair_id: str = Field(min_length=1, max_length=120)
    seed: int = Field(ge=0, le=2_147_483_647)
    variant_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    replay_key: str = Field(min_length=1, max_length=160)


class ExecutionOutcome(ClosedModel):
    agent_claimed_success: bool = False
    terminal_reason: str = Field(min_length=1, max_length=80)
    error_code: str = Field(default="NONE", min_length=1, max_length=80)
    final_state: dict[str, Any] | None = None
    oracle_result: dict[str, Any] | None = None
    step_count: int = Field(default=0, ge=0)
    recovery_count: int = Field(default=0, ge=0)
    intervention_count: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    infrastructure_error: str | None = Field(default=None, max_length=2_000)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(ClosedModel):
    schema_version: str = "evaluation-v1"
    run: ManifestRun
    config_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt: int = Field(ge=1)
    agent_claimed_success: bool
    oracle_success: bool | None
    outcome_pass: bool | None
    safety_pass: bool | None
    failure_class: FailureClass
    terminal_reason: str
    error_code: str
    step_count: int = Field(ge=0)
    recovery_count: int = Field(ge=0)
    intervention_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    oracle: dict[str, Any] | None = None
    infrastructure_error: str | None = None
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def resumable_complete(self) -> bool:
        return self.failure_class is not FailureClass.INFRASTRUCTURE
