"""Deterministic safety gate and explicit approval lifecycle for Stage 11."""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from packages.agent.contracts import AgentAction, ClosedModel, RiskLevel

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "safety_policy.yaml"


def utc_now() -> datetime:
    return datetime.now(UTC)


class RiskClass(StrEnum):
    LOW_RISK = "LOW_RISK"
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
    FORBIDDEN = "FORBIDDEN"


class ApprovalChoice(StrEnum):
    APPROVE = "APPROVE"
    EDIT = "EDIT"
    REJECT = "REJECT"
    TAKE_OVER = "TAKE_OVER"
    CANCEL = "CANCEL"


class DecisionActor(StrEnum):
    AGENT = "AGENT"
    USER = "USER"
    POLICY = "POLICY"


class InputChannel(StrEnum):
    KEYBOARD = "KEYBOARD"
    VOICE = "VOICE"


class SafetyPolicyConfig(ClosedModel):
    schema_version: str
    policy_id: str
    scope: str
    risk_classes: list[RiskClass]
    forbidden_patterns: list[str]
    confirm_patterns: list[str]
    voice_approval_phrases: list[str]
    keyboard_shortcuts: dict[ApprovalChoice, str]


class SafetyDecision(ClosedModel):
    decision_id: UUID = Field(default_factory=uuid4)
    step_id: UUID
    risk_class: RiskClass
    policy_id: str
    target: str
    reason: str
    decided_by: DecisionActor = DecisionActor.POLICY
    decided_at: datetime = Field(default_factory=utc_now)
    model_risk_level: RiskLevel


class ApprovalOption(ClosedModel):
    choice: ApprovalChoice
    label: str
    shortcut: str


class ApprovalCard(ClosedModel):
    approval_id: UUID = Field(default_factory=uuid4)
    step_id: UUID
    action: str
    target: str
    impact: str
    announcement: str
    options: list[ApprovalOption]
    default_choice: ApprovalChoice = ApprovalChoice.REJECT
    approve_requires_explicit_activation: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalResolution(ClosedModel):
    approval_id: UUID
    step_id: UUID
    choice: ApprovalChoice
    actor: DecisionActor = DecisionActor.USER
    channel: InputChannel
    announced_transcript: str | None = None
    resolved_at: datetime = Field(default_factory=utc_now)
    consumed_at: datetime | None = None


class SafetyPolicy:
    """Classify from policy and semantic target; planner risk can only raise risk."""

    def __init__(self, config: SafetyPolicyConfig) -> None:
        self.config = config
        self._forbidden = tuple(re.compile(item, re.IGNORECASE) for item in config.forbidden_patterns)
        self._confirm = tuple(re.compile(item, re.IGNORECASE) for item in config.confirm_patterns)

    @classmethod
    def load(cls, path: Path = DEFAULT_POLICY_PATH) -> SafetyPolicy:
        # JSON is a strict YAML subset, keeping this safety-critical loader dependency-free.
        return cls(SafetyPolicyConfig.model_validate(json.loads(path.read_text(encoding="utf-8"))))

    @staticmethod
    def _descriptor(action: AgentAction, target_name: str | None) -> str:
        return " | ".join(
            part for part in (action.action_type.value, target_name, action.expected_effect) if part
        )

    def classify(self, action: AgentAction, *, target_name: str | None = None) -> SafetyDecision:
        descriptor = self._descriptor(action, target_name)
        target = target_name or action.target_ref or action.action_type.value
        forbidden = next((pattern.pattern for pattern in self._forbidden if pattern.search(descriptor)), None)
        if forbidden:
            risk_class = RiskClass.FORBIDDEN
            reason = f"Policy forbidden pattern matched: {forbidden}"
        else:
            confirm = next((pattern.pattern for pattern in self._confirm if pattern.search(descriptor)), None)
            model_raised = action.risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH} or action.requires_approval
            if confirm or model_raised:
                risk_class = RiskClass.CONFIRM_REQUIRED
                reason = (
                    f"Policy confirm pattern matched: {confirm}"
                    if confirm
                    else "Planner requested equal-or-higher protection; policy did not downgrade it."
                )
            else:
                risk_class = RiskClass.LOW_RISK
                reason = "No deterministic sensitive-action rule matched."
        return SafetyDecision(
            step_id=action.step_id,
            risk_class=risk_class,
            policy_id=self.config.policy_id,
            target=target,
            reason=reason,
            model_risk_level=action.risk_level,
        )

    def approval_card(self, action: AgentAction, decision: SafetyDecision) -> ApprovalCard:
        if decision.risk_class is not RiskClass.CONFIRM_REQUIRED:
            raise ValueError("Approval card hanya untuk CONFIRM_REQUIRED")
        labels = {
            ApprovalChoice.APPROVE: "Setujui",
            ApprovalChoice.EDIT: "Ubah",
            ApprovalChoice.REJECT: "Tolak",
            ApprovalChoice.TAKE_OVER: "Ambil alih",
            ApprovalChoice.CANCEL: "Batalkan tugas",
        }
        order = [
            ApprovalChoice.REJECT,
            ApprovalChoice.CANCEL,
            ApprovalChoice.EDIT,
            ApprovalChoice.TAKE_OVER,
            ApprovalChoice.APPROVE,
        ]
        options = [
            ApprovalOption(
                choice=choice,
                label=labels[choice],
                shortcut=self.config.keyboard_shortcuts[choice],
            )
            for choice in order
        ]
        impact = action.expected_effect
        announcement = (
            f"Konfirmasi diperlukan. Tindakan {action.action_type.value} pada {decision.target}. "
            f"Akibat: {impact}. Pilihan awal Tolak."
        )
        return ApprovalCard(
            step_id=action.step_id,
            action=action.action_type.value,
            target=decision.target,
            impact=impact,
            announcement=announcement,
            options=options,
        )


class ApprovalRegistry:
    """Thread-safe, explicit and one-shot approval store used across graph pauses."""

    def __init__(self, policy: SafetyPolicy) -> None:
        self.policy = policy
        self._lock = threading.RLock()
        self._cards: dict[UUID, ApprovalCard] = {}
        self._resolutions: dict[UUID, ApprovalResolution] = {}

    def register(self, card: ApprovalCard) -> None:
        with self._lock:
            self._cards.setdefault(card.approval_id, card)

    def resolve(
        self,
        approval_id: UUID,
        *,
        choice: ApprovalChoice,
        channel: InputChannel = InputChannel.KEYBOARD,
        voice_transcript: str | None = None,
    ) -> ApprovalResolution:
        with self._lock:
            if approval_id in self._resolutions:
                raise RuntimeError("Approval sudah memiliki outcome final.")
            card = self._cards.get(approval_id)
            if card is None:
                raise KeyError("Approval tidak terdaftar.")
            announced = None
            if channel is InputChannel.VOICE:
                def normalize_phrase(value: str) -> str:
                    normalized = unicodedata.normalize("NFKC", value).casefold()
                    return " ".join(
                        "".join(character if character.isalnum() else " " for character in normalized).split()
                    )

                announced = normalize_phrase(voice_transcript or "")
                allowed = {normalize_phrase(item) for item in self.policy.config.voice_approval_phrases}
                if choice is ApprovalChoice.APPROVE and announced not in allowed:
                    raise ValueError("Voice approval harus eksplisit dan cocok dengan frasa policy.")
            resolution = ApprovalResolution(
                approval_id=approval_id,
                step_id=card.step_id,
                choice=choice,
                channel=channel,
                announced_transcript=announced,
            )
            self._resolutions[approval_id] = resolution
            return resolution

    def consume_approval(self, approval_id: UUID, *, step_id: UUID) -> ApprovalResolution:
        with self._lock:
            resolution = self._resolutions.get(approval_id)
            if resolution is None or resolution.choice is not ApprovalChoice.APPROVE:
                raise PermissionError("Approval eksplisit belum diberikan.")
            if resolution.step_id != step_id:
                raise PermissionError("Approval tidak berlaku untuk action ini.")
            if resolution.consumed_at is not None:
                raise RuntimeError("Approval sudah dikonsumsi; double execution diblokir.")
            consumed = resolution.model_copy(update={"consumed_at": utc_now()})
            self._resolutions[approval_id] = consumed
            return consumed

    def audit_snapshot(self, approval_id: UUID) -> dict[str, Any]:
        with self._lock:
            card = self._cards[approval_id]
            resolution = self._resolutions.get(approval_id)
            return {
                "card": card.model_dump(mode="json"),
                "resolution": resolution.model_dump(mode="json") if resolution else None,
            }


def execute_with_consumed_approval(
    *,
    registry: ApprovalRegistry,
    approval_id: UUID,
    action: AgentAction,
    executor: Any,
    page: Any,
    control_gate: Any,
) -> Any:
    """Consume once before execution, so reconnect/double click cannot replay an action."""

    registry.consume_approval(approval_id, step_id=action.step_id)
    lease = control_gate.begin_action()
    try:
        return executor.execute(page, action, approval_granted=True)
    finally:
        control_gate.finish_action(lease)
