"""Typed state, privacy, and persistence boundary for the research agent."""

from packages.agent.contracts import (
    AgentAction,
    AgentState,
    AXNode,
    ErrorCode,
    GoalSpec,
    Observation,
    RiskLevel,
    TerminalReason,
    VerificationResult,
    VerificationStatus,
)
from packages.agent.executor import DeterministicExecutor, PrimitiveAction, PrimitiveActionRequest
from packages.agent.observer import AccessibilityObserver
from packages.agent.predicates import ExpectedPostcondition, PredicateKind, VerificationPlan
from packages.agent.recovery import RecoveryController, RecoveryPolicy
from packages.agent.resolver import SemanticTargetResolver
from packages.agent.semantic_snapshot import SnapshotRegistry, TargetQuery
from packages.agent.verifier import PredicateVerifier

__all__ = [
    "AXNode",
    "AccessibilityObserver",
    "AgentAction",
    "AgentState",
    "ErrorCode",
    "ExpectedPostcondition",
    "DeterministicExecutor",
    "GoalSpec",
    "Observation",
    "PrimitiveAction",
    "PrimitiveActionRequest",
    "PredicateKind",
    "PredicateVerifier",
    "RecoveryController",
    "RecoveryPolicy",
    "RiskLevel",
    "SnapshotRegistry",
    "SemanticTargetResolver",
    "TargetQuery",
    "TerminalReason",
    "VerificationResult",
    "VerificationPlan",
    "VerificationStatus",
]
