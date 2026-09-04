"""Single-agent LangGraph orchestration for observe-plan-act-verify-recover."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.agent.contracts import ErrorCode, VerificationStatus
from backend.agent.executor import DeterministicExecutor
from backend.agent.observer import AccessibilityObserver
from backend.agent.planner import (
    NormalizedGoal,
    PlannerDecision,
    PlannerRequest,
    StructuredPlanner,
    apply_user_correction,
    clarify_if_needed,
    normalize_input,
)
from backend.agent.predicates import VerificationPlan
from backend.agent.recovery import RecoveryContext, RecoveryController, RecoveryDecision
from backend.agent.safety import ApprovalRegistry, RiskClass, SafetyPolicy
from backend.agent.semantic_snapshot import render_compact
from backend.agent.shared_control import AtomicControlGate, ConstraintUpdate, ResumeResult
from backend.agent.state import AgentGraphState
from backend.agent.verifier import PredicateVerifier


class GraphRoute(StrEnum):
    EXECUTE = "EXECUTE"
    INTERRUPT = "INTERRUPT"
    VERIFY = "VERIFY"
    RECOVER = "RECOVER"
    OBSERVE = "OBSERVE"
    REPLAN = "REPLAN"
    RECONCILE = "RECONCILE"
    FINISH = "FINISH"
    ABORT = "ABORT"
    SAFETY_STOP = "SAFETY_STOP"


STATE_DIAGRAM = """flowchart TD
  START-->observe-->update_task_map-->plan-->policy_check
  policy_check-->|EXECUTE|execute-->verify
  policy_check-->|INTERRUPT|interrupt-->focus_handoff-->END
  policy_check-->|SAFETY_STOP|safety_stop-->END
  verify-->|VERIFIED|reconcile_task_map
  verify-->|FAILED/UNCERTAIN|recover
  recover-->|OBSERVE|observe
  recover-->|REPLAN|plan
  recover-->|INTERRUPT|interrupt
  recover-->|ABORT|abort-->END
  reconcile_task_map-->|continue|observe
  reconcile_task_map-->|complete|finish-->END
"""


@dataclass
class OrchestrationServices:
    page: Any
    observer: AccessibilityObserver
    executor: DeterministicExecutor
    verifier: PredicateVerifier
    planner: StructuredPlanner
    recovery: RecoveryController
    safety: SafetyPolicy | None = None
    approvals: ApprovalRegistry | None = None
    control: AtomicControlGate | None = None

    def __post_init__(self) -> None:
        self.safety = self.safety or SafetyPolicy.load()
        self.approvals = self.approvals or ApprovalRegistry(self.safety)
        self.control = self.control or AtomicControlGate()


@dataclass(frozen=True, slots=True)
class GraphFeatures:
    """Treatment switches; defaults preserve the proposed agent behavior."""

    bounded_recovery: bool = True


def apply_correction_to_state(state: AgentGraphState, correction: str) -> AgentGraphState:
    """Version a user correction without replacing session/thread/run identity."""
    goal = apply_user_correction(
        normalize_input(state["raw_input"])
        if not state.get("normalized_goal")
        else NormalizedGoal.model_validate(state["normalized_goal"]),
        correction,
    )
    version = state.get("constraint_version", 0) + 1
    entry = ConstraintUpdate(
        version=version,
        user_text=correction,
        goal_before=(state.get("normalized_goal") or {}).get("objective", state["raw_input"]),
        goal_after=goal.objective,
        constraints_after=goal.constraints,
    )
    return AgentGraphState(
        normalized_goal=goal.model_dump(mode="json"),
        raw_input=goal.objective,
        active_semantic_ref=None,
        task_map_version=state.get("task_map_version", 0) + 1,
        constraint_version=version,
        conversation_log=[
            *state.get("conversation_log", []),
            entry.model_dump(mode="json"),
        ],
    )


def apply_resume_to_state(state: AgentGraphState, resume: ResumeResult) -> AgentGraphState:
    """Invalidate stale refs and require replan from the resume observation."""

    return AgentGraphState(
        observation_version=resume.fresh_observation_version,
        task_map_version=resume.task_map_version,
        active_semantic_ref=None,
        planner_decision=None,
        state_delta=resume.state_delta.model_dump(mode="json"),
        invalidated_semantic_refs=resume.invalidated_semantic_refs,
        handoff_status=resume.handoff_status.value,
        pending_interrupt=None,
        route=GraphRoute.OBSERVE.value,
    )


def _route(state: AgentGraphState) -> str:
    return GraphRoute(state["route"]).value


def build_agent_graph(
    services: OrchestrationServices,
    *,
    checkpointer: Any = None,
    features: GraphFeatures | None = None,
):
    active_features = features or GraphFeatures()
    builder = StateGraph(AgentGraphState)

    def normalize(state: AgentGraphState) -> AgentGraphState:
        goal = normalize_input(state["raw_input"])
        clarification = clarify_if_needed(goal)
        if clarification:
            return AgentGraphState(
                normalized_goal=goal.model_dump(mode="json"),
                pending_interrupt={"kind": "CLARIFICATION", "announcement": clarification},
                route=GraphRoute.INTERRUPT.value,
            )
        return AgentGraphState(normalized_goal=goal.model_dump(mode="json"))

    def normalize_route(state: AgentGraphState) -> str:
        return GraphRoute.INTERRUPT.value if state.get("pending_interrupt") else GraphRoute.OBSERVE.value

    def observe(state: AgentGraphState) -> AgentGraphState:
        observation = services.observer.capture(services.page)
        return AgentGraphState(
            observation_version=observation.version,
            observation_ref=str(observation.observation_ref),
            compact_observation=render_compact(observation),
            active_semantic_ref=None,
        )

    def update_task_map(state: AgentGraphState) -> AgentGraphState:
        return AgentGraphState(task_map_version=state.get("task_map_version", 0) + 1)

    def plan(state: AgentGraphState) -> AgentGraphState:
        max_steps = int(state.get("max_steps", 30))
        token_budget = int(state.get("token_budget", 20_000))
        request = PlannerRequest(
            compact_observation=state["compact_observation"],
            goal=state["normalized_goal"],
            verified_progress=state.get("verified_progress", []),
            relevant_items=state.get("relevant_items", []),
            remaining_steps=max(0, max_steps - state.get("step_count", 0)),
            remaining_tokens=max(0, token_budget - state.get("token_usage", 0)),
            last_verification=state.get("verification"),
        )
        try:
            decision, telemetry = services.planner.plan(request)
        except RuntimeError as exc:
            return AgentGraphState(
                error_code=ErrorCode.INTERNAL_ERROR.value,
                pending_interrupt={"kind": "PLANNER_FAILURE", "announcement": str(exc)},
                route=GraphRoute.ABORT.value,
            )
        logs = [*state.get("planner_telemetry", []), telemetry.model_dump(mode="json")]
        return AgentGraphState(
            planner_decision=decision.model_dump(mode="json"),
            planner_telemetry=logs,
            token_usage=state.get("token_usage", 0) + telemetry.input_tokens + telemetry.output_tokens,
            route=GraphRoute.EXECUTE.value,
        )

    def policy_check(state: AgentGraphState) -> AgentGraphState:
        decision = PlannerDecision.model_validate(state["planner_decision"])
        action = decision.action
        target_name = None
        if action.target_ref:
            try:
                target_name = services.observer.node_for_ref(action.target_ref).name
            except Exception:
                target_name = None
        safety_decision = services.safety.classify(action, target_name=target_name)
        if safety_decision.risk_class is RiskClass.FORBIDDEN:
            return AgentGraphState(
                safety_decision=safety_decision.model_dump(mode="json"),
                pending_interrupt={
                    "kind": "SAFETY_BLOCK",
                    "action": action.model_dump(mode="json"),
                    "announcement": "Aksi dilarang oleh kebijakan eksperimen dan tidak dijalankan.",
                },
                intervention_count=state.get("intervention_count", 0) + 1,
                error_code=ErrorCode.POLICY_BLOCKED.value,
                route=GraphRoute.SAFETY_STOP.value,
            )
        if safety_decision.risk_class is RiskClass.CONFIRM_REQUIRED:
            card = services.safety.approval_card(action, safety_decision)
            services.approvals.register(card)
            return AgentGraphState(
                safety_decision=safety_decision.model_dump(mode="json"),
                approval_card=card.model_dump(mode="json"),
                pending_interrupt={
                    "kind": "APPROVAL",
                    "action": action.model_dump(mode="json"),
                    "approval_id": str(card.approval_id),
                    "announcement": card.announcement,
                },
                intervention_count=state.get("intervention_count", 0) + 1,
                route=GraphRoute.INTERRUPT.value,
            )
        return AgentGraphState(
            safety_decision=safety_decision.model_dump(mode="json"),
            route=GraphRoute.EXECUTE.value,
        )

    def execute(state: AgentGraphState) -> AgentGraphState:
        decision = PlannerDecision.model_validate(state["planner_decision"])
        try:
            lease = services.control.begin_action()
        except PermissionError as exc:
            return AgentGraphState(
                pending_interrupt={"kind": str(exc), "announcement": "Agen berhenti di checkpoint aman."},
                intervention_count=state.get("intervention_count", 0) + 1,
                route=GraphRoute.INTERRUPT.value,
            )
        try:
            result = services.executor.execute(services.page, decision.action)
        finally:
            services.control.finish_action(lease)
        return AgentGraphState(
            execution=result.model_dump(mode="json"),
            step_count=state.get("step_count", 0) + 1,
            error_code=result.error_code.value,
            route=(
                GraphRoute.VERIFY.value
                if result.success
                else GraphRoute.RECOVER.value
                if active_features.bounded_recovery
                else GraphRoute.ABORT.value
            ),
        )

    def verify(state: AgentGraphState) -> AgentGraphState:
        decision = PlannerDecision.model_validate(state["planner_decision"])
        execution = state["execution"]
        plan_obj = VerificationPlan(
            step_id=decision.action.step_id,
            before_observation_ref=state["observation_ref"],
            predicates=decision.postconditions,
            planned_at=state["planner_telemetry"][-1]["recorded_at"],
        )
        result, evidence = services.verifier.verify(
            services.page,
            plan_obj,
            execution_started_at=datetime.fromisoformat(execution["started_at"]),
        )
        route = (
            GraphRoute.RECONCILE
            if result.status is VerificationStatus.VERIFIED
            else GraphRoute.RECOVER
            if active_features.bounded_recovery
            else GraphRoute.ABORT
        )
        return AgentGraphState(
            verification=result.model_dump(mode="json"),
            verification_evidence=[item.model_dump(mode="json") for item in evidence],
            route=route.value,
        )

    def recover(state: AgentGraphState) -> AgentGraphState:
        decision = PlannerDecision.model_validate(state["planner_decision"])
        verification = state.get("verification") or {}
        context = RecoveryContext(
            step_id=decision.action.step_id,
            verification_status=verification.get("status", VerificationStatus.FAILED.value),
            error_code=state.get("error_code", ErrorCode.VERIFICATION_FAILED.value),
            risk_level=decision.action.risk_level,
            requires_approval=decision.action.requires_approval,
            approval_consumed=decision.action.requires_approval,
            recovery_cycle=state.get("recovery_count", 0),
            replan_count=state.get("replan_count", 0),
            step_count=state.get("step_count", 0),
            runtime_ms=max(0, int(time.time() * 1_000) - state.get("started_at_ms", 0)),
        )
        outcome = services.recovery.decide(context)
        mapping = {
            RecoveryDecision.WAIT_REOBSERVE: GraphRoute.OBSERVE,
            RecoveryDecision.RERESOLVE: GraphRoute.OBSERVE,
            RecoveryDecision.RETRY: GraphRoute.OBSERVE,
            RecoveryDecision.REPLAN: GraphRoute.REPLAN,
            RecoveryDecision.ASK_USER: GraphRoute.INTERRUPT,
            RecoveryDecision.ABORT: GraphRoute.ABORT,
        }
        update = AgentGraphState(
            recovery_count=state.get("recovery_count", 0) + 1,
            route=mapping[outcome.decision].value,
        )
        if outcome.decision is RecoveryDecision.REPLAN:
            update["replan_count"] = state.get("replan_count", 0) + 1
        if outcome.decision is RecoveryDecision.ASK_USER:
            update["pending_interrupt"] = {"kind": "RECOVERY", "announcement": outcome.reason}
        return update

    def reconcile_task_map(state: AgentGraphState) -> AgentGraphState:
        decision = PlannerDecision.model_validate(state["planner_decision"])
        progress = [*state.get("verified_progress", []), decision.action.expected_effect]
        return AgentGraphState(
            verified_progress=progress,
            task_map_version=state.get("task_map_version", 0) + 1,
            route=(
                GraphRoute.FINISH if decision.goal_complete_after_verification else GraphRoute.OBSERVE
            ).value,
        )

    def interrupt_node(state: AgentGraphState) -> AgentGraphState:
        return AgentGraphState(route=GraphRoute.INTERRUPT.value)

    def focus_handoff(state: AgentGraphState) -> AgentGraphState:
        return AgentGraphState(handoff_status="REQUESTED")

    def resync(state: AgentGraphState) -> AgentGraphState:
        return AgentGraphState(active_semantic_ref=None, route=GraphRoute.OBSERVE.value)

    def finish(state: AgentGraphState) -> AgentGraphState:
        return AgentGraphState(terminal_reason="COMPLETED", error_code=ErrorCode.NONE.value)

    def abort(state: AgentGraphState) -> AgentGraphState:
        return AgentGraphState(terminal_reason="ERROR")

    def safety_stop(state: AgentGraphState) -> AgentGraphState:
        return AgentGraphState(
            terminal_reason="SAFETY_STOP",
            error_code=ErrorCode.POLICY_BLOCKED.value,
        )

    nodes = {
        "normalize_input": normalize,
        "observe": observe,
        "update_task_map": update_task_map,
        "plan": plan,
        "policy_check": policy_check,
        "execute": execute,
        "verify": verify,
        "recover": recover,
        "interrupt": interrupt_node,
        "focus_handoff": focus_handoff,
        "resync": resync,
        "reconcile_task_map": reconcile_task_map,
        "finish": finish,
        "abort": abort,
        "safety_stop": safety_stop,
    }
    for name, function in nodes.items():
        builder.add_node(name, function)
    builder.add_edge(START, "normalize_input")
    builder.add_conditional_edges(
        "normalize_input",
        normalize_route,
        {GraphRoute.INTERRUPT.value: "interrupt", GraphRoute.OBSERVE.value: "observe"},
    )
    builder.add_edge("observe", "update_task_map")
    builder.add_edge("update_task_map", "plan")
    builder.add_conditional_edges(
        "plan", _route, {GraphRoute.ABORT.value: "abort", GraphRoute.EXECUTE.value: "policy_check"}
    )
    builder.add_conditional_edges(
        "policy_check",
        _route,
        {
            GraphRoute.EXECUTE.value: "execute",
            GraphRoute.INTERRUPT.value: "interrupt",
            GraphRoute.SAFETY_STOP.value: "safety_stop",
        },
    )
    builder.add_conditional_edges(
        "execute",
        _route,
        {
            GraphRoute.VERIFY.value: "verify",
            GraphRoute.RECOVER.value: "recover",
            GraphRoute.INTERRUPT.value: "interrupt",
            GraphRoute.ABORT.value: "abort",
        },
    )
    builder.add_conditional_edges(
        "verify",
        _route,
        {
            GraphRoute.RECONCILE.value: "reconcile_task_map",
            GraphRoute.RECOVER.value: "recover",
            GraphRoute.ABORT.value: "abort",
        },
    )
    builder.add_conditional_edges(
        "recover",
        _route,
        {
            GraphRoute.OBSERVE.value: "observe",
            GraphRoute.REPLAN.value: "plan",
            GraphRoute.INTERRUPT.value: "interrupt",
            GraphRoute.ABORT.value: "abort",
        },
    )
    builder.add_conditional_edges(
        "reconcile_task_map", _route, {GraphRoute.OBSERVE.value: "observe", GraphRoute.FINISH.value: "finish"}
    )
    builder.add_edge("interrupt", "focus_handoff")
    builder.add_edge("focus_handoff", END)
    builder.add_edge("resync", "observe")
    builder.add_edge("finish", END)
    builder.add_edge("abort", END)
    builder.add_edge("safety_stop", END)
    return builder.compile(checkpointer=checkpointer)
