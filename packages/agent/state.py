"""LangGraph state shape kept intentionally free of planner/executor logic."""

from __future__ import annotations

from typing import Any, TypedDict

from packages.agent.contracts import AgentState


class AgentGraphState(TypedDict, total=False):
    schema_version: str
    session_id: str
    thread_id: str
    run_id: str
    task_id: str
    goal: dict[str, Any]
    constraints: list[str]
    observation_version: int
    task_map_version: int
    active_semantic_ref: str | None
    verification: dict[str, Any] | None
    handoff_status: str
    step_count: int
    recovery_count: int
    intervention_count: int
    pending_interrupt: dict[str, Any] | None
    terminal_reason: str | None
    error_code: str


def to_graph_state(state: AgentState) -> AgentGraphState:
    """Serialize one validated Pydantic state into checkpointer-safe primitives."""

    return AgentGraphState(**state.model_dump(mode="json"))
