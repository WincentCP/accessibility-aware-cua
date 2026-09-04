"""Typed state, privacy, and persistence boundary for the research agent."""

from backend.agent.contracts import (
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
from backend.agent.executor import DeterministicExecutor, PrimitiveAction, PrimitiveActionRequest
from backend.agent.graph import OrchestrationServices, apply_resume_to_state, build_agent_graph
from backend.agent.observer import AccessibilityObserver
from backend.agent.planner import PlannerDecision, StructuredPlanner, normalize_input
from backend.agent.predicates import ExpectedPostcondition, PredicateKind, VerificationPlan
from backend.agent.recovery import RecoveryController, RecoveryPolicy
from backend.agent.resolver import SemanticTargetResolver
from backend.agent.safety import ApprovalRegistry, RiskClass, SafetyPolicy
from backend.agent.semantic_snapshot import SnapshotRegistry, TargetQuery
from backend.agent.shared_control import AtomicControlGate, SharedControlService
from backend.agent.task_map import AccessibleTaskMap, TaskMapCompiler
from backend.agent.verifier import PredicateVerifier

__all__ = [
    "AXNode",
    "AccessibilityObserver",
    "AccessibleTaskMap",
    "AgentAction",
    "AgentState",
    "ApprovalRegistry",
    "AtomicControlGate",
    "ErrorCode",
    "ExpectedPostcondition",
    "DeterministicExecutor",
    "GoalSpec",
    "Observation",
    "OrchestrationServices",
    "PlannerDecision",
    "PrimitiveAction",
    "PrimitiveActionRequest",
    "PredicateKind",
    "PredicateVerifier",
    "RecoveryController",
    "RecoveryPolicy",
    "RiskClass",
    "RiskLevel",
    "SafetyPolicy",
    "SharedControlService",
    "SnapshotRegistry",
    "StructuredPlanner",
    "SemanticTargetResolver",
    "TargetQuery",
    "TaskMapCompiler",
    "TerminalReason",
    "VerificationResult",
    "VerificationPlan",
    "VerificationStatus",
    "build_agent_graph",
    "apply_resume_to_state",
    "normalize_input",
]
