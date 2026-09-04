"""Auditable, verified-only task-map compiler for the accessible extension."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from backend.agent.contracts import (
    AgentAction,
    ClosedModel,
    HandoffStatus,
    Observation,
    RelevantItem,
    VerificationResult,
    VerificationStatus,
)

TASK_MAP_SCHEMA_VERSION = "1.0.0"


def utc_now() -> datetime:
    return datetime.now(UTC)


class DisplayStatus(StrEnum):
    VERIFIED_COMPLETED = "VERIFIED_COMPLETED"
    PLANNED = "PLANNED"
    UNCERTAIN = "UNCERTAIN"
    RELEVANT = "RELEVANT"


class MapControlState(ClosedModel):
    paused: bool = False
    takeover_active: bool = False
    approval_pending: bool = False
    handoff_status: HandoffStatus = HandoffStatus.NONE


class TaskMapItem(ClosedModel):
    item_id: UUID = Field(default_factory=uuid4)
    label: str = Field(min_length=1, max_length=2_000)
    status: DisplayStatus
    semantic_ref: str | None = Field(default=None, max_length=256)
    observation_version: int = Field(ge=1)
    verification_id: UUID | None = None
    evidence: list[str] = Field(default_factory=list, max_length=32)
    reason: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_provenance(self) -> TaskMapItem:
        if self.status is DisplayStatus.VERIFIED_COMPLETED and (
            self.verification_id is None or not self.evidence
        ):
            raise ValueError("Completed claim wajib memiliki verification_id dan evidence.")
        if self.status in {DisplayStatus.PLANNED, DisplayStatus.RELEVANT} and not self.semantic_ref:
            raise ValueError(f"{self.status.value} item wajib memiliki semantic_ref.")
        return self


class AccessibleTaskMap(ClosedModel):
    schema_version: str = TASK_MAP_SCHEMA_VERSION
    map_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    run_id: UUID
    version: int = Field(ge=1)
    observation_version: int = Field(ge=1)
    goal: str = Field(min_length=1, max_length=4_000)
    progress_label: str = Field(min_length=1, max_length=500)
    verified_completed: list[TaskMapItem] = Field(default_factory=list)
    relevant_options: list[TaskMapItem] = Field(default_factory=list)
    next_action: TaskMapItem | None = None
    uncertain_items: list[TaskMapItem] = Field(default_factory=list)
    control_state: MapControlState = Field(default_factory=MapControlState)
    final_summary: str | None = Field(default=None, max_length=4_000)
    stale_invalidated_count: int = Field(default=0, ge=0)
    generated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def enforce_separate_status_buckets(self) -> AccessibleTaskMap:
        if any(item.status is not DisplayStatus.VERIFIED_COMPLETED for item in self.verified_completed):
            raise ValueError("Bucket completed hanya menerima VERIFIED_COMPLETED.")
        if any(item.status is not DisplayStatus.RELEVANT for item in self.relevant_options):
            raise ValueError("Bucket relevant hanya menerima RELEVANT.")
        if any(item.status is not DisplayStatus.UNCERTAIN for item in self.uncertain_items):
            raise ValueError("Bucket uncertain hanya menerima UNCERTAIN.")
        if self.next_action and self.next_action.status is not DisplayStatus.PLANNED:
            raise ValueError("next_action wajib berstatus PLANNED.")
        return self


class TaskMapCompileInput(ClosedModel):
    session_id: UUID
    run_id: UUID
    version: int = Field(ge=1)
    goal: str = Field(min_length=1, max_length=4_000)
    observation: Observation
    verifications: list[VerificationResult] = Field(default_factory=list)
    effect_by_step_id: dict[str, str] = Field(default_factory=dict)
    planned_action: AgentAction | None = None
    relevant_items: list[RelevantItem] = Field(default_factory=list)
    control_state: MapControlState = Field(default_factory=MapControlState)
    final_summary: str | None = Field(default=None, max_length=4_000)


class TaskMapCompiler:
    """Compile extension view from trusted verification and fresh observation state."""

    def compile(self, source: TaskMapCompileInput) -> AccessibleTaskMap:
        current_version = source.observation.version
        stale_count = 0
        completed: list[TaskMapItem] = []
        uncertain: list[TaskMapItem] = []

        for verification in source.verifications:
            label = source.effect_by_step_id.get(str(verification.step_id))
            if not label:
                continue
            if verification.status is VerificationStatus.VERIFIED:
                completed.append(
                    TaskMapItem(
                        label=label,
                        status=DisplayStatus.VERIFIED_COMPLETED,
                        observation_version=current_version,
                        verification_id=verification.verification_id,
                        evidence=verification.evidence,
                    )
                )
            elif verification.status in {
                VerificationStatus.FAILED,
                VerificationStatus.INCONCLUSIVE,
                VerificationStatus.UNCERTAIN,
                VerificationStatus.STALE,
            }:
                uncertain.append(
                    TaskMapItem(
                        label=label,
                        status=DisplayStatus.UNCERTAIN,
                        observation_version=current_version,
                        verification_id=verification.verification_id,
                        evidence=verification.evidence,
                        reason=f"Verification status: {verification.status.value}",
                    )
                )

        relevant: list[TaskMapItem] = []
        for item in source.relevant_items:
            if item.observation_version != current_version:
                stale_count += 1
                continue
            relevant.append(
                TaskMapItem(
                    label=item.label,
                    status=DisplayStatus.RELEVANT,
                    semantic_ref=item.semantic_ref,
                    observation_version=current_version,
                    reason=item.reason,
                )
            )

        planned = None
        action = source.planned_action
        if action is not None:
            if action.observation_version != current_version or not action.target_ref:
                stale_count += 1
            else:
                planned = TaskMapItem(
                    label=action.expected_effect,
                    status=DisplayStatus.PLANNED,
                    semantic_ref=action.target_ref,
                    observation_version=current_version,
                    reason=f"Action planned: {action.action_type.value}",
                )

        completed_count = len(completed)
        uncertain_count = len(uncertain)
        progress = f"{completed_count} langkah terverifikasi selesai"
        if uncertain_count:
            progress += f"; {uncertain_count} langkah belum pasti"
        return AccessibleTaskMap(
            session_id=source.session_id,
            run_id=source.run_id,
            version=source.version,
            observation_version=current_version,
            goal=source.goal,
            progress_label=progress,
            verified_completed=completed,
            relevant_options=relevant,
            next_action=planned,
            uncertain_items=uncertain,
            control_state=source.control_state,
            final_summary=source.final_summary,
            stale_invalidated_count=stale_count,
        )


def task_map_json_schema() -> dict[str, Any]:
    return AccessibleTaskMap.model_json_schema()
