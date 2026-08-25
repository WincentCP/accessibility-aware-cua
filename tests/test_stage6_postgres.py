from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from packages.agent.checkpoints import build_checkpoint_graph, postgres_checkpointer
from packages.agent.contracts import (
    AgentAction,
    AgentState,
    ErrorCode,
    FocusHandoff,
    GoalSpec,
    InputModality,
    InterventionKind,
    InterventionStatus,
    MessageRole,
    RunResult,
    TaskMapSnapshot,
    TerminalReason,
    VerificationResult,
    VerificationStatus,
)
from packages.agent.persistence import AuditRepository
from packages.agent.retention import RetentionPolicy, purge_expired_sessions
from packages.agent.state import to_graph_state

POSTGRES_REQUIRED = os.getenv("CUA_REQUIRE_POSTGRES", "false").lower() == "true"
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://cua:cua_local_only@127.0.0.1:5432/cua"
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_REQUIRED,
    reason="Set CUA_REQUIRE_POSTGRES=true to run the real PostgreSQL Stage 6 gate.",
)


@pytest.fixture(scope="module")
def repository() -> AuditRepository:
    repo = AuditRepository(DATABASE_URL)
    repo.rollback()
    repo.migrate()
    with postgres_checkpointer(DATABASE_URL, setup=True):
        pass
    return repo


def _goal() -> GoalSpec:
    return GoalSpec(
        task_id="T01",
        objective="Pilih rute valid dan berhenti sebelum booking.",
        constraints=["Jangan booking"],
        allowed_actions=["click", "wait"],
        max_steps=16,
        risk_level="LOW",
    )


def test_migration_v1_builds_required_tables_from_empty_database(repository: AuditRepository) -> None:
    required = {
        "sessions",
        "messages",
        "task_runs",
        "agent_steps",
        "verifications",
        "task_map_snapshots",
        "focus_handoffs",
        "interventions",
        "experiment_configs",
        "checkpoints",
    }
    with repository.connection() as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
        version = connection.execute(
            "SELECT version FROM schema_migrations WHERE version = '001_stage6'"
        ).fetchone()
    assert required <= {row["tablename"] for row in rows}
    assert version["version"] == "001_stage6"


def test_audit_can_reconstruct_run_query_metrics_and_survive_restart(
    repository: AuditRepository,
) -> None:
    session_id = uuid4()
    run_id = uuid4()
    before_ref = uuid4()
    after_ref = uuid4()
    intervention_id = uuid4()
    action = AgentAction(
        action_type="type",
        target_ref="origin-input",
        input_value="password=NeverPersistThis",
        observation_version=1,
        expected_effect="Asal terisi",
    )
    verification = VerificationResult(
        step_id=action.step_id,
        status="VERIFIED",
        evidence=["Accessible value summary berubah"],
        before_observation_ref=before_ref,
        after_observation_ref=after_ref,
    )

    repository.start_session(
        session_id=session_id,
        thread_id=f"session:{session_id}",
        input_modality=InputModality.VOICE_TRANSCRIPT,
    )
    repository.append_message(
        message_id=uuid4(),
        session_id=session_id,
        role=MessageRole.USER,
        content="Tujuan dengan otp=918273 harus dimasking",
    )
    repository.save_experiment_config(
        config_hash="config-sha256",
        model_id="deterministic-stage6-probe",
        prompt_hash="prompt-sha256",
        browser_version="chromium-stage6",
        seed=101,
        payload={"api_key": "sk-NeverPersistThis", "temperature": 0},
    )
    repository.start_run(
        run_id=run_id,
        session_id=session_id,
        task_id="T01",
        condition_id="C2",
        config_hash="config-sha256",
        model_id="deterministic-stage6-probe",
        prompt_hash="prompt-sha256",
        browser_version="chromium-stage6",
        seed=101,
        goal={
            "objective": "Pilih rute",
            "api_key": "sk-NeverPersistThis",
            "raw_audio": "NeverPersistAudio",
        },
    )
    repository.append_step(
        run_id=run_id,
        step_index=0,
        before_observation_ref=before_ref,
        after_observation_ref=after_ref,
        action=action,
        verification_status=VerificationStatus.VERIFIED,
        latency_ms=123,
    )
    repository.add_verification(run_id=run_id, result=verification)
    repository.save_task_map(
        TaskMapSnapshot(
            session_id=session_id,
            run_id=run_id,
            version=1,
            observation_version=2,
            completed_items=["Asal terisi"],
            pending_items=["Pilih rute"],
        )
    )
    repository.save_focus_handoff(
        FocusHandoff(
            run_id=run_id,
            status="REQUESTED",
            target_ref="origin-input",
            announcement="Kontrol diserahkan ke pengguna",
        ),
        step_id=action.step_id,
    )
    repository.record_intervention(
        intervention_id=intervention_id,
        run_id=run_id,
        step_id=action.step_id,
        kind=InterventionKind.APPROVAL,
        status=InterventionStatus.PENDING,
        reason="Konfirmasi aksi berisiko",
        payload={"otp": "918273", "choice": "belum dijawab"},
    )
    repository.finish_run(
        RunResult(
            run_id=run_id,
            success=True,
            terminal_reason=TerminalReason.COMPLETED,
            error_code=ErrorCode.NONE,
            step_count=1,
            recovery_count=0,
            intervention_count=1,
            duration_ms=250,
        )
    )

    restarted_repository = AuditRepository(DATABASE_URL)
    reconstructed = restarted_repository.reconstruct_run(run_id)
    assert reconstructed is not None
    assert reconstructed["run"]["config_hash"] == "config-sha256"
    assert reconstructed["steps"][0]["before_observation_ref"] == before_ref
    assert reconstructed["steps"][0]["after_observation_ref"] == after_ref
    assert reconstructed["steps"][0]["verification_status"] == "VERIFIED"
    assert reconstructed["experiment_config"]["prompt_hash"] == "prompt-sha256"
    assert reconstructed["task_maps"][0]["observation_version"] == 2
    assert reconstructed["focus_handoffs"][0]["status"] == "REQUESTED"
    assert restarted_repository.pending_interventions(run_id)[0]["intervention_id"] == intervention_id
    restarted_repository.resolve_intervention(
        intervention_id=intervention_id,
        status=InterventionStatus.APPROVED,
        actor="USER",
        outcome="APPROVE",
    )
    resolved = restarted_repository.reconstruct_run(run_id)["interventions"][0]
    assert resolved["status"] == "APPROVED"
    assert resolved["resolved_at"] is not None
    assert resolved["payload"]["actor"] == "USER"
    assert resolved["payload"]["outcome"] == "APPROVE"
    with pytest.raises(RuntimeError, match="sudah memiliki outcome"):
        restarted_repository.resolve_intervention(
            intervention_id=intervention_id,
            status=InterventionStatus.APPROVED,
            actor="USER",
            outcome="APPROVE",
        )

    serialized = json.dumps(reconstructed, default=str)
    assert "NeverPersistThis" not in serialized
    assert "NeverPersistAudio" not in serialized
    assert "918273" not in serialized

    metrics = restarted_repository.metric_summary()
    assert metrics["total_runs"] >= 1
    assert metrics["successful_runs"] >= 1
    assert metrics["mean_duration_ms"] >= 0


def test_langgraph_pending_interrupt_resumes_after_new_process_boundary(
    repository: AuditRepository,
) -> None:
    session_id = uuid4()
    run_id = uuid4()
    thread_id = f"session:{session_id}"
    state = AgentState(
        session_id=session_id,
        thread_id=thread_id,
        run_id=run_id,
        task_id="T01",
        goal=_goal(),
        pending_interrupt={
            "kind": "APPROVAL",
            "status": "PENDING",
            "announcement": "Konfirmasi sebelum melanjutkan",
        },
        intervention_count=1,
        task_map_version=3,
        handoff_status="REQUESTED",
    )
    config = {"configurable": {"thread_id": thread_id}}

    with postgres_checkpointer(DATABASE_URL) as first_saver:
        first_graph = build_checkpoint_graph(first_saver)
        first_graph.invoke(to_graph_state(state), config)

    # A new saver and compiled graph simulate an API process restart.
    with postgres_checkpointer(DATABASE_URL) as restarted_saver:
        restarted_graph = build_checkpoint_graph(restarted_saver)
        snapshot = restarted_graph.get_state(config)

    assert snapshot.values["run_id"] == str(run_id)
    assert snapshot.values["pending_interrupt"]["status"] == "PENDING"
    assert snapshot.values["intervention_count"] == 1
    assert snapshot.values["task_map_version"] == 3
    assert snapshot.values["handoff_status"] == "REQUESTED"


def test_retention_deletes_expired_audit_and_matching_checkpoint(
    repository: AuditRepository,
) -> None:
    now = datetime.now(UTC)
    session_id = uuid4()
    run_id = uuid4()
    thread_id = f"expired:{session_id}"
    repository.start_session(
        session_id=session_id,
        thread_id=thread_id,
        input_modality=InputModality.TEXT,
    )
    repository.end_session(session_id, ended_at=now - timedelta(days=91))
    state = AgentState(
        session_id=session_id,
        thread_id=thread_id,
        run_id=run_id,
        task_id="T01",
        goal=_goal(),
    )
    config = {"configurable": {"thread_id": thread_id}}
    with postgres_checkpointer(DATABASE_URL) as saver:
        graph = build_checkpoint_graph(saver)
        graph.invoke(to_graph_state(state), config)
        assert graph.get_state(config).values["run_id"] == str(run_id)

    deleted = purge_expired_sessions(DATABASE_URL, RetentionPolicy(), now=now)
    assert deleted == 1

    with repository.connection() as connection:
        session = connection.execute(
            "SELECT session_id FROM sessions WHERE session_id = %s", (session_id,)
        ).fetchone()
    with postgres_checkpointer(DATABASE_URL) as restarted_saver:
        restarted_graph = build_checkpoint_graph(restarted_saver)
        snapshot = restarted_graph.get_state(config)
    assert session is None
    assert snapshot.values == {}
