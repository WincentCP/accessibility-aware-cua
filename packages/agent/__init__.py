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
from packages.agent.observer import AccessibilityObserver
from packages.agent.semantic_snapshot import SnapshotRegistry, TargetQuery

__all__ = [
    "AXNode",
    "AccessibilityObserver",
    "AgentAction",
    "AgentState",
    "ErrorCode",
    "GoalSpec",
    "Observation",
    "RiskLevel",
    "SnapshotRegistry",
    "TargetQuery",
    "TerminalReason",
    "VerificationResult",
    "VerificationStatus",
]
