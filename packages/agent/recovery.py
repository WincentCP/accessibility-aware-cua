"""Bounded recovery ladder and auditable safe-abstention decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from packages.agent.contracts import (
    ClosedModel,
    ErrorCode,
    RiskLevel,
    TerminalReason,
    VerificationResult,
    VerificationStatus,
)


class RecoveryDecision(StrEnum):
    WAIT_REOBSERVE = "WAIT_REOBSERVE"
    RERESOLVE = "RERESOLVE"
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    ASK_USER = "ASK_USER"
    ABORT = "ABORT"


class RecoveryPolicy(ClosedModel):
    max_recovery_cycles_per_action: int = Field(default=2, ge=0, le=5)
    max_replans_per_task: int = Field(default=3, ge=0, le=10)
    max_steps: int = Field(default=30, ge=1, le=100)
    max_runtime_ms: int = Field(default=120_000, ge=1_000, le=900_000)
    bounded_wait_ms: int = Field(default=750, ge=0, le=5_000)


class RecoveryContext(ClosedModel):
    step_id: UUID
    verification_status: VerificationStatus
    error_code: ErrorCode = ErrorCode.VERIFICATION_FAILED
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    approval_consumed: bool = False
    recovery_cycle: int = Field(default=0, ge=0)
    replan_count: int = Field(default=0, ge=0)
    step_count: int = Field(default=0, ge=0)
    runtime_ms: int = Field(default=0, ge=0)


class RecoveryOutcome(ClosedModel):
    recovery_id: UUID = Field(default_factory=uuid4)
    step_id: UUID
    decision: RecoveryDecision
    reason: str = Field(min_length=1, max_length=2_000)
    recovery_cycle: int = Field(ge=0)
    terminal_reason: TerminalReason | None = None
    approval_required: bool = False
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecoveryController:
    def __init__(self, policy: RecoveryPolicy | None = None) -> None:
        self.policy = policy or RecoveryPolicy()

    def decide(self, context: RecoveryContext) -> RecoveryOutcome:
        if context.verification_status is VerificationStatus.VERIFIED:
            raise ValueError("Recovery hanya untuk FAILED/UNCERTAIN/STALE")
        if context.step_count >= self.policy.max_steps:
            return self._abort(context, TerminalReason.MAX_STEPS, "Global max_steps tercapai.")
        if context.runtime_ms >= self.policy.max_runtime_ms:
            return self._abort(context, TerminalReason.ERROR, "Global max_runtime tercapai.")
        if context.recovery_cycle >= self.policy.max_recovery_cycles_per_action:
            if context.replan_count < self.policy.max_replans_per_task:
                return self._outcome(
                    context, RecoveryDecision.REPLAN, "Recovery action habis; replan dari observasi baru."
                )
            return self._outcome(
                context,
                RecoveryDecision.ASK_USER,
                "Batas recovery dan replan tercapai; abstain dan minta pengguna.",
            )
        if context.recovery_cycle == 0:
            return self._outcome(
                context,
                RecoveryDecision.WAIT_REOBSERVE,
                f"Tunggu maksimal {self.policy.bounded_wait_ms} ms lalu observasi ulang.",
            )
        if context.error_code in {
            ErrorCode.STALE_OBSERVATION,
            ErrorCode.TARGET_NOT_FOUND,
            ErrorCode.AMBIGUOUS_TARGET,
        }:
            return self._outcome(
                context, RecoveryDecision.RERESOLVE, "Buang ref lama dan resolve dari snapshot baru."
            )
        sensitive = context.risk_level is RiskLevel.HIGH or context.requires_approval
        if sensitive and context.approval_consumed:
            return RecoveryOutcome(
                step_id=context.step_id,
                decision=RecoveryDecision.ASK_USER,
                reason="Retry sensitif memerlukan approval baru.",
                recovery_cycle=context.recovery_cycle,
                approval_required=True,
            )
        return self._outcome(
            context, RecoveryDecision.RETRY, "Retry satu kali dari observasi dan locator baru."
        )

    @staticmethod
    def _outcome(context: RecoveryContext, decision: RecoveryDecision, reason: str) -> RecoveryOutcome:
        return RecoveryOutcome(
            step_id=context.step_id,
            decision=decision,
            reason=reason,
            recovery_cycle=context.recovery_cycle,
        )

    @staticmethod
    def _abort(context: RecoveryContext, terminal: TerminalReason, reason: str) -> RecoveryOutcome:
        return RecoveryOutcome(
            step_id=context.step_id,
            decision=RecoveryDecision.ABORT,
            reason=reason,
            recovery_cycle=context.recovery_cycle,
            terminal_reason=terminal,
        )


class CompletedClaim(ClosedModel):
    item: str = Field(min_length=1, max_length=2_000)
    verification: VerificationResult
    evidence_ref: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @model_validator(mode="after")
    def require_verified_provenance(self) -> CompletedClaim:
        if self.verification.status is not VerificationStatus.VERIFIED:
            raise ValueError("Task map tidak boleh completed tanpa VERIFIED")
        if self.evidence_ref not in self.verification.evidence:
            raise ValueError("evidence_ref harus berasal dari VerificationResult")
        return self


class HiddenOracleVerdict(ClosedModel):
    source: Literal["hidden_oracle"] = "hidden_oracle"
    passed: bool


def final_success_from_hidden_oracle(verdict: HiddenOracleVerdict) -> bool:
    """The only permitted final-success boundary; planner finish is intentionally absent."""
    return verdict.passed
