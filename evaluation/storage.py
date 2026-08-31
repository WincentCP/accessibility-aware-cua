"""Result stores for resumable evaluation runs."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from evaluation.contracts import EvaluationResult


class ResultStore(Protocol):
    def latest(self, run_id: str) -> EvaluationResult | None: ...

    def save(self, result: EvaluationResult) -> None: ...

    def all_results(self) -> list[EvaluationResult]: ...


class MemoryResultStore:
    def __init__(self, results: Iterable[EvaluationResult] = ()) -> None:
        self._results = list(results)

    def latest(self, run_id: str) -> EvaluationResult | None:
        matches = [result for result in self._results if result.run.run_id == run_id]
        return max(matches, key=lambda item: item.attempt, default=None)

    def save(self, result: EvaluationResult) -> None:
        self._results.append(result)

    def all_results(self) -> list[EvaluationResult]:
        return list(self._results)


class JsonResultStore(MemoryResultStore):
    """Atomic local fallback useful for development and interrupted dry runs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            results = [EvaluationResult.model_validate(item) for item in payload.get("results", [])]
        else:
            results = []
        super().__init__(results)

    def save(self, result: EvaluationResult) -> None:
        super().save(result)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {
            "schema_version": "evaluation-v1",
            "results": [item.model_dump(mode="json") for item in self._results],
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)


class PostgresResultStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connection(self):
        return psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=5)

    def latest(self, run_id: str) -> EvaluationResult | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT result_payload FROM evaluation_runs
                WHERE manifest_run_id = %s
                ORDER BY attempt DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        return EvaluationResult.model_validate(row["result_payload"]) if row else None

    def save(self, result: EvaluationResult) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_runs (
                    manifest_run_id, attempt, split, task_id, condition_id,
                    configuration, pair_id, seed, config_hash, failure_class,
                    oracle_success, result_payload, completed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (manifest_run_id, attempt)
                DO UPDATE SET result_payload = EXCLUDED.result_payload,
                              failure_class = EXCLUDED.failure_class,
                              oracle_success = EXCLUDED.oracle_success,
                              completed_at = EXCLUDED.completed_at
                """,
                (
                    result.run.run_id,
                    result.attempt,
                    result.run.split,
                    result.run.task_id,
                    result.run.condition_id,
                    result.run.configuration.value,
                    result.run.pair_id,
                    result.run.seed,
                    result.config_hash,
                    result.failure_class.value,
                    result.oracle_success,
                    Jsonb(result.model_dump(mode="json")),
                    result.completed_at,
                ),
            )

    def all_results(self) -> list[EvaluationResult]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT result_payload FROM evaluation_runs ORDER BY completed_at, manifest_run_id, attempt"
            ).fetchall()
        return [EvaluationResult.model_validate(row["result_payload"]) for row in rows]
