"""PostgreSQL migration and typed audit adapter for reproducible experiments."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from packages.agent.contracts import (
    AgentAction,
    ErrorCode,
    FocusHandoff,
    InputModality,
    InterventionKind,
    InterventionStatus,
    MessageRole,
    RunResult,
    TaskMapSnapshot,
    VerificationResult,
    VerificationStatus,
)
from packages.agent.privacy import redact_payload

MIGRATION_DIR = Path(__file__).resolve().parent / "migrations"


class AuditRepository:
    """Write structured audit records only after validation and redaction."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(
            self.database_url, row_factory=dict_row, connect_timeout=5
        ) as connection:
            yield connection

    def migrate(self) -> None:
        with self.connection() as connection:
            for migration in sorted(MIGRATION_DIR.glob("*_up.sql")):
                connection.execute(migration.read_text(encoding="utf-8"))

    def rollback(self) -> None:
        with self.connection() as connection:
            for migration in sorted(MIGRATION_DIR.glob("*_down.sql"), reverse=True):
                connection.execute(migration.read_text(encoding="utf-8"))

    def start_session(
        self, *, session_id: UUID, thread_id: str, input_modality: InputModality
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO sessions (session_id, thread_id, input_modality)
                VALUES (%s, %s, %s)
                ON CONFLICT (session_id) DO NOTHING
                """,
                (session_id, thread_id, input_modality.value),
            )

    def append_message(
        self, *, message_id: UUID, session_id: UUID, role: MessageRole, content: str
    ) -> None:
        safe_content = redact_payload(content)
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO messages (message_id, session_id, role, content)
                VALUES (%s, %s, %s, %s)
                """,
                (message_id, session_id, role.value, safe_content),
            )

    def save_experiment_config(
        self,
        *,
        config_hash: str,
        model_id: str,
        prompt_hash: str,
        browser_version: str,
        seed: int,
        payload: dict[str, Any],
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO experiment_configs (
                    config_hash, model_id, prompt_hash, browser_version, seed, config_payload
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (config_hash) DO NOTHING
                """,
                (
                    config_hash,
                    model_id,
                    prompt_hash,
                    browser_version,
                    seed,
                    Jsonb(redact_payload(payload)),
                ),
            )

    def end_session(self, session_id: UUID, *, ended_at: datetime | None = None) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE sessions SET ended_at = coalesce(%s, now()) WHERE session_id = %s",
                (ended_at, session_id),
            )

    def expired_sessions(self, cutoff: datetime) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT session_id, thread_id FROM sessions
                WHERE ended_at IS NOT NULL AND ended_at < %s
                ORDER BY ended_at
                """,
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_sessions(self, session_ids: list[UUID]) -> int:
        if not session_ids:
            return 0
        with self.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE session_id = ANY(%s)", (session_ids,)
            )
            return cursor.rowcount

    def start_run(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        task_id: str,
        condition_id: str,
        config_hash: str,
        model_id: str,
        prompt_hash: str,
        browser_version: str,
        seed: int,
        goal: dict[str, Any],
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO task_runs (
                    run_id, session_id, task_id, condition_id, config_hash, model_id,
                    prompt_hash, browser_version, seed, goal_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    session_id,
                    task_id,
                    condition_id,
                    config_hash,
                    model_id,
                    prompt_hash,
                    browser_version,
                    seed,
                    Jsonb(redact_payload(goal)),
                ),
            )

    def append_step(
        self,
        *,
        run_id: UUID,
        step_index: int,
        before_observation_ref: UUID,
        after_observation_ref: UUID | None,
        action: AgentAction,
        verification_status: VerificationStatus,
        latency_ms: int,
        error_code: ErrorCode = ErrorCode.NONE,
    ) -> None:
        safe_action = redact_payload(action.model_dump(mode="json"))
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_steps (
                    step_id, run_id, step_index, before_observation_ref,
                    after_observation_ref, observation_version, action_type,
                    action_payload, verification_status, risk_level, latency_ms, error_code
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    action.step_id,
                    run_id,
                    step_index,
                    before_observation_ref,
                    after_observation_ref,
                    action.observation_version,
                    action.action_type.value,
                    Jsonb(safe_action),
                    verification_status.value,
                    action.risk_level.value,
                    latency_ms,
                    error_code.value,
                ),
            )

    def add_verification(self, *, run_id: UUID, result: VerificationResult) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO verifications (
                    verification_id, run_id, step_id, status, evidence,
                    before_observation_ref, after_observation_ref, error_code, checked_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    result.verification_id,
                    run_id,
                    result.step_id,
                    result.status.value,
                    Jsonb(redact_payload(result.evidence)),
                    result.before_observation_ref,
                    result.after_observation_ref,
                    result.error_code.value,
                    result.checked_at,
                ),
            )

    def save_task_map(self, snapshot: TaskMapSnapshot) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO task_map_snapshots (
                    snapshot_id, run_id, version, observation_version, snapshot_payload, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.run_id,
                    snapshot.version,
                    snapshot.observation_version,
                    Jsonb(redact_payload(snapshot.model_dump(mode="json"))),
                    snapshot.created_at,
                ),
            )

    def save_focus_handoff(self, handoff: FocusHandoff, *, step_id: UUID | None = None) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO focus_handoffs (
                    handoff_id, run_id, step_id, status, target_ref, announcement, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    handoff.handoff_id,
                    handoff.run_id,
                    step_id,
                    handoff.status.value,
                    handoff.target_ref,
                    redact_payload(handoff.announcement),
                    handoff.created_at,
                ),
            )

    def record_intervention(
        self,
        *,
        intervention_id: UUID,
        run_id: UUID,
        step_id: UUID | None,
        kind: InterventionKind,
        status: InterventionStatus,
        reason: str,
        payload: dict[str, Any],
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO interventions (
                    intervention_id, run_id, step_id, kind, status, reason, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    intervention_id,
                    run_id,
                    step_id,
                    kind.value,
                    status.value,
                    reason,
                    Jsonb(redact_payload(payload)),
                ),
            )

    def resolve_intervention(
        self,
        *,
        intervention_id: UUID,
        status: InterventionStatus,
        actor: str,
        outcome: str,
        resolved_at: datetime | None = None,
    ) -> None:
        if status is InterventionStatus.PENDING:
            raise ValueError("Outcome final tidak boleh memakai status PENDING.")
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE interventions
                SET status = %s,
                    payload = payload || %s,
                    resolved_at = coalesce(%s, now())
                WHERE intervention_id = %s AND status = 'PENDING'
                """,
                (
                    status.value,
                    Jsonb(redact_payload({"actor": actor, "outcome": outcome})),
                    resolved_at,
                    intervention_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Intervention tidak pending atau sudah memiliki outcome.")

    def finish_run(self, result: RunResult) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE task_runs SET
                    completed_at = now(), success = %s, terminal_reason = %s,
                    error_code = %s, step_count = %s, recovery_count = %s,
                    intervention_count = %s, duration_ms = %s
                WHERE run_id = %s
                """,
                (
                    result.success,
                    result.terminal_reason.value,
                    result.error_code.value,
                    result.step_count,
                    result.recovery_count,
                    result.intervention_count,
                    result.duration_ms,
                    result.run_id,
                ),
            )

    def reconstruct_run(self, run_id: UUID) -> dict[str, Any] | None:
        with self.connection() as connection:
            run = connection.execute(
                "SELECT * FROM task_runs WHERE run_id = %s", (run_id,)
            ).fetchone()
            if run is None:
                return None
            messages = connection.execute(
                "SELECT * FROM messages WHERE session_id = %s ORDER BY created_at",
                (run["session_id"],),
            ).fetchall()
            experiment_config = connection.execute(
                "SELECT * FROM experiment_configs WHERE config_hash = %s",
                (run["config_hash"],),
            ).fetchone()
            steps = connection.execute(
                "SELECT * FROM agent_steps WHERE run_id = %s ORDER BY step_index", (run_id,)
            ).fetchall()
            verifications = connection.execute(
                "SELECT * FROM verifications WHERE run_id = %s ORDER BY checked_at", (run_id,)
            ).fetchall()
            interventions = connection.execute(
                "SELECT * FROM interventions WHERE run_id = %s ORDER BY created_at", (run_id,)
            ).fetchall()
            task_maps = connection.execute(
                "SELECT * FROM task_map_snapshots WHERE run_id = %s ORDER BY version", (run_id,)
            ).fetchall()
            focus_handoffs = connection.execute(
                "SELECT * FROM focus_handoffs WHERE run_id = %s ORDER BY created_at", (run_id,)
            ).fetchall()
        return {
            "run": dict(run),
            "messages": [dict(row) for row in messages],
            "experiment_config": dict(experiment_config) if experiment_config else None,
            "steps": [dict(row) for row in steps],
            "verifications": [dict(row) for row in verifications],
            "interventions": [dict(row) for row in interventions],
            "task_maps": [dict(row) for row in task_maps],
            "focus_handoffs": [dict(row) for row in focus_handoffs],
        }

    def pending_interventions(self, run_id: UUID) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM interventions
                WHERE run_id = %s AND status = 'PENDING'
                ORDER BY created_at
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def metric_summary(self) -> dict[str, Any]:
        """Query Bab 4 metrics from typed columns, never by parsing text logs."""

        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    count(*) AS total_runs,
                    count(*) FILTER (WHERE success) AS successful_runs,
                    coalesce(avg(duration_ms), 0)::float AS mean_duration_ms,
                    coalesce(avg(step_count), 0)::float AS mean_step_count,
                    coalesce(avg(intervention_count), 0)::float AS mean_intervention_count
                FROM task_runs
                WHERE completed_at IS NOT NULL
                """
            ).fetchone()
        return dict(row)
