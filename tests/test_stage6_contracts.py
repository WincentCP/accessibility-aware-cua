from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.agent.contracts import (
    AgentAction,
    AgentState,
    GoalSpec,
    RiskLevel,
    VerificationResult,
    VerificationStatus,
)
from backend.agent.state import to_graph_state

ROOT = Path(__file__).resolve().parents[1]


def sample_goal() -> GoalSpec:
    return GoalSpec(
        task_id="T01",
        objective="Pilih rute valid lalu berhenti di halaman review.",
        constraints=["Jangan booking"],
        allowed_actions=["navigate", "click", "wait"],
        max_steps=16,
        risk_level="LOW",
    )


def test_invalid_action_payload_is_rejected_before_executor() -> None:
    with pytest.raises(ValidationError, match="target_ref wajib"):
        AgentAction(
            action_type="click",
            observation_version=1,
            expected_effect="Membuka hasil",
        )

    with pytest.raises(ValidationError):
        AgentAction(
            action_type="invented_action",
            observation_version=1,
            expected_effect="Tidak valid",
        )

    with pytest.raises(ValidationError, match="HIGH wajib"):
        AgentAction(
            action_type="click",
            target_ref="button-submit",
            observation_version=1,
            expected_effect="Mengirim perubahan",
            risk_level=RiskLevel.HIGH,
        )


def test_verified_claim_requires_after_observation_and_evidence() -> None:
    with pytest.raises(ValidationError, match="VERIFIED wajib"):
        VerificationResult(
            step_id=uuid4(),
            status=VerificationStatus.VERIFIED,
            before_observation_ref=uuid4(),
        )


def test_langgraph_state_uses_validated_json_primitives() -> None:
    session_id = uuid4()
    run_id = uuid4()
    state = AgentState(
        session_id=session_id,
        thread_id=f"session:{session_id}",
        run_id=run_id,
        task_id="T01",
        goal=sample_goal(),
        constraints=["synthetic_only"],
        pending_interrupt={"kind": "APPROVAL", "status": "PENDING"},
    )
    graph_state = to_graph_state(state)
    assert graph_state["session_id"] == str(session_id)
    assert graph_state["goal"]["allowed_actions"] == ["navigate", "click", "wait"]
    assert graph_state["pending_interrupt"]["status"] == "PENDING"


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GoalSpec(
            task_id="T01",
            objective="Tujuan",
            allowed_actions=["wait"],
            max_steps=1,
            risk_level="LOW",
            arbitrary_planner_text="tidak boleh lolos",
        )


def test_empty_database_rollback_is_idempotent() -> None:
    down_sql = (
        ROOT / "backend" / "agent" / "migrations" / "001_stage6_down.sql"
    ).read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS schema_migrations" in down_sql
    assert "DELETE FROM schema_migrations" not in down_sql
