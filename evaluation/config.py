"""Locked treatment definitions for fair B0/B1/P comparisons.

The configuration object is deliberately explicit. A run cannot silently inherit
features from the proposed system, and an unavailable baseline fails preflight
instead of being substituted with a different modality.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import Field, model_validator

from packages.agent.contracts import ClosedModel


class EvaluationConfiguration(StrEnum):
    B0 = "B0"
    B1 = "B1"
    PROPOSED = "P"


class TreatmentConfig(ClosedModel):
    configuration: EvaluationConfiguration
    label: str = Field(min_length=1, max_length=120)
    observation_mode: str = Field(pattern=r"^(?:screenshot|accessibility_tree)$")
    action_grounding: str = Field(pattern=r"^(?:coordinates|semantic_ref)$")
    post_action_verification: bool
    bounded_recovery: bool
    verified_task_map: bool
    focus_synchronized_handoff: bool
    runtime_adapter: str = Field(min_length=1, max_length=80)
    implementation_ready: bool
    unavailable_reason: str | None = None
    model_family: str = "gemini"
    temperature: float = 0.0
    token_budget: int = 20_000
    safety_policy: str = "shared-v1"
    prompt_family: str = "planner-v1"

    @model_validator(mode="after")
    def unavailable_config_requires_reason(self) -> TreatmentConfig:
        if not self.implementation_ready and not self.unavailable_reason:
            raise ValueError("Konfigurasi yang belum siap wajib menjelaskan alasannya.")
        if self.configuration is EvaluationConfiguration.B0:
            if self.observation_mode != "screenshot" or self.action_grounding != "coordinates":
                raise ValueError("B0 wajib tetap visual; tidak boleh diganti accessibility tree.")
        else:
            if self.observation_mode != "accessibility_tree" or self.action_grounding != "semantic_ref":
                raise ValueError("B1/P wajib memakai accessibility tree dan semantic refs.")
        return self

    @property
    def config_hash(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def require_ready(self) -> None:
        if not self.implementation_ready:
            raise RuntimeError(
                f"{self.configuration.value} belum dapat dijalankan: {self.unavailable_reason}"
            )


CONFIGURATIONS: dict[EvaluationConfiguration, TreatmentConfig] = {
    EvaluationConfiguration.B0: TreatmentConfig(
        configuration=EvaluationConfiguration.B0,
        label="Baseline visual berbasis screenshot dan koordinat",
        observation_mode="screenshot",
        action_grounding="coordinates",
        post_action_verification=True,
        bounded_recovery=False,
        verified_task_map=False,
        focus_synchronized_handoff=False,
        runtime_adapter="visual-coordinate-v1",
        implementation_ready=True,
        prompt_family="visual-baseline-v1",
    ),
    EvaluationConfiguration.B1: TreatmentConfig(
        configuration=EvaluationConfiguration.B1,
        label="Baseline semantic satu kali act-verify",
        observation_mode="accessibility_tree",
        action_grounding="semantic_ref",
        post_action_verification=True,
        bounded_recovery=False,
        verified_task_map=False,
        focus_synchronized_handoff=False,
        runtime_adapter="semantic-basic-v1",
        implementation_ready=True,
    ),
    EvaluationConfiguration.PROPOSED: TreatmentConfig(
        configuration=EvaluationConfiguration.PROPOSED,
        label="Accessibility-aware agent yang diusulkan",
        observation_mode="accessibility_tree",
        action_grounding="semantic_ref",
        post_action_verification=True,
        bounded_recovery=True,
        verified_task_map=True,
        focus_synchronized_handoff=True,
        runtime_adapter="semantic-proposed-v1",
        implementation_ready=True,
    ),
}


def validate_treatment_isolation() -> None:
    """Assert shared factors and the intended treatment deltas."""

    configs = list(CONFIGURATIONS.values())
    shared_fields = (
        "model_family",
        "temperature",
        "token_budget",
        "safety_policy",
        "post_action_verification",
    )
    for field in shared_fields:
        values = {getattr(config, field) for config in configs}
        if len(values) != 1:
            raise ValueError(f"Faktor bersama berubah antar-treatment: {field}")
    if CONFIGURATIONS[EvaluationConfiguration.B1].bounded_recovery:
        raise ValueError("B1 tidak boleh mewarisi bounded recovery milik P.")
    if not CONFIGURATIONS[EvaluationConfiguration.PROPOSED].bounded_recovery:
        raise ValueError("P wajib mengaktifkan bounded recovery.")


validate_treatment_isolation()
