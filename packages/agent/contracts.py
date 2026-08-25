"""Versioned, closed contracts shared by agent components and audit storage."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"


def utc_now() -> datetime:
    return datetime.now(UTC)


class ClosedModel(BaseModel):
    """Reject unknown fields so malformed planner output cannot reach an executor."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class InputModality(StrEnum):
    TEXT = "text"
    VOICE_TRANSCRIPT = "voice_transcript"


class ActionType(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    PRESS = "press"
    SCROLL = "scroll"
    WAIT = "wait"
    BACK = "back"
    ASK_USER = "ask_user"
    HANDOFF = "handoff"
    STOP = "stop"


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    STALE = "STALE"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TerminalReason(StrEnum):
    COMPLETED = "COMPLETED"
    USER_STOP = "USER_STOP"
    MAX_STEPS = "MAX_STEPS"
    SAFETY_STOP = "SAFETY_STOP"
    ERROR = "ERROR"


class ErrorCode(StrEnum):
    NONE = "NONE"
    INVALID_ACTION = "INVALID_ACTION"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    USER_TAKEOVER = "USER_TAKEOVER"
    MAX_STEPS_REACHED = "MAX_STEPS_REACHED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class HandoffStatus(StrEnum):
    NONE = "NONE"
    REQUESTED = "REQUESTED"
    ACTIVE = "ACTIVE"
    RESUMING = "RESUMING"
    COMPLETED = "COMPLETED"


class MessageRole(StrEnum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class InterventionKind(StrEnum):
    APPROVAL = "APPROVAL"
    TAKEOVER = "TAKEOVER"
    CLARIFICATION = "CLARIFICATION"
    CANCEL = "CANCEL"


class InterventionStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class UserCommand(ClosedModel):
    schema_version: str = SCHEMA_VERSION
    command_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    text: str = Field(min_length=1, max_length=4_000)
    modality: InputModality = InputModality.TEXT
    received_at: datetime = Field(default_factory=utc_now)


class GoalSpec(ClosedModel):
    schema_version: str = SCHEMA_VERSION
    task_id: str = Field(pattern=r"^T(?:0[1-9]|1[0-2])$")
    objective: str = Field(min_length=1, max_length=4_000)
    constraints: list[str] = Field(default_factory=list, max_length=32)
    allowed_actions: list[ActionType] = Field(min_length=1)
    max_steps: int = Field(ge=1, le=100)
    risk_level: RiskLevel


class AXNode(ClosedModel):
    node_id: str = Field(min_length=1, max_length=256)
    role: str = Field(min_length=1, max_length=128)
    name: str = Field(default="", max_length=1_000)
    description: str | None = Field(default=None, max_length=2_000)
    value_summary: str | None = Field(default=None, max_length=1_000)
    disabled: bool = False
    focused: bool = False
    children: list[str] = Field(default_factory=list)


class Observation(ClosedModel):
    schema_version: str = SCHEMA_VERSION
    observation_ref: UUID = Field(default_factory=uuid4)
    version: int = Field(ge=1)
    url: str = Field(min_length=1, max_length=4_000)
    title: str = Field(default="", max_length=1_000)
    captured_at: datetime = Field(default_factory=utc_now)
    nodes: list[AXNode] = Field(default_factory=list)
    focused_node_id: str | None = None


class AgentAction(ClosedModel):
    schema_version: str = SCHEMA_VERSION
    step_id: UUID = Field(default_factory=uuid4)
    action_type: ActionType
    target_ref: str | None = Field(default=None, max_length=256)
    input_value: str | None = Field(default=None, max_length=4_000)
    key: str | None = Field(default=None, max_length=64)
    observation_version: int = Field(ge=1)
    expected_effect: str = Field(min_length=1, max_length=2_000)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False

    @model_validator(mode="after")
    def validate_action_shape(self) -> AgentAction:
        target_actions = {
            ActionType.CLICK,
            ActionType.TYPE,
            ActionType.SELECT,
            ActionType.CHECK,
            ActionType.UNCHECK,
        }
        if self.action_type in target_actions and not self.target_ref:
            raise ValueError(f"target_ref wajib untuk action {self.action_type.value}")
        if self.action_type in {ActionType.TYPE, ActionType.SELECT} and self.input_value is None:
            raise ValueError(f"input_value wajib untuk action {self.action_type.value}")
        if self.action_type is ActionType.PRESS and not self.key:
            raise ValueError("key wajib untuk action press")
        if self.risk_level is RiskLevel.HIGH and not self.requires_approval:
            raise ValueError("action HIGH wajib requires_approval=true")
        return self


class VerificationResult(ClosedModel):
    schema_version: str = SCHEMA_VERSION
    verification_id: UUID = Field(default_factory=uuid4)
    step_id: UUID
    status: VerificationStatus
    evidence: list[str] = Field(default_factory=list, max_length=32)
    before_observation_ref: UUID
    after_observation_ref: UUID | None = None
    checked_at: datetime = Field(default_factory=utc_now)
    error_code: ErrorCode = ErrorCode.NONE

    @model_validator(mode="after")
    def verified_requires_after_evidence(self) -> VerificationResult:
        if self.status is VerificationStatus.VERIFIED and (
            self.after_observation_ref is None or not self.evidence
        ):
            raise ValueError("VERIFIED wajib memiliki after_observation_ref dan evidence")
        return self


class RelevantItem(ClosedModel):
    semantic_ref: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=1_000)
    reason: str = Field(min_length=1, max_length=2_000)
    observation_version: int = Field(ge=1)


class TaskMapSnapshot(ClosedModel):
    schema_version: str = SCHEMA_VERSION
    snapshot_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    run_id: UUID
    version: int = Field(ge=1)
    observation_version: int = Field(ge=1)
    completed_items: list[str] = Field(default_factory=list)
    pending_items: list[str] = Field(default_factory=list)
    relevant_items: list[RelevantItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class FocusHandoff(ClosedModel):
    schema_version: str = SCHEMA_VERSION
    handoff_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    status: HandoffStatus
    target_ref: str | None = Field(default=None, max_length=256)
    announcement: str = Field(min_length=1, max_length=2_000)
    created_at: datetime = Field(default_factory=utc_now)


class AgentState(ClosedModel):
    schema_version: str = SCHEMA_VERSION
    session_id: UUID
    thread_id: str = Field(min_length=1, max_length=256)
    run_id: UUID
    task_id: str = Field(pattern=r"^T(?:0[1-9]|1[0-2])$")
    goal: GoalSpec
    constraints: list[str] = Field(default_factory=list)
    observation_version: int = Field(default=0, ge=0)
    task_map_version: int = Field(default=0, ge=0)
    active_semantic_ref: str | None = None
    verification: VerificationResult | None = None
    handoff_status: HandoffStatus = HandoffStatus.NONE
    step_count: int = Field(default=0, ge=0)
    recovery_count: int = Field(default=0, ge=0)
    intervention_count: int = Field(default=0, ge=0)
    pending_interrupt: dict[str, Any] | None = None
    terminal_reason: TerminalReason | None = None
    error_code: ErrorCode = ErrorCode.NONE


class RunResult(ClosedModel):
    schema_version: str = SCHEMA_VERSION
    run_id: UUID
    success: bool
    terminal_reason: TerminalReason
    error_code: ErrorCode = ErrorCode.NONE
    step_count: int = Field(ge=0)
    recovery_count: int = Field(ge=0)
    intervention_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
