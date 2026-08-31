"""Manifest-driven, resumable runner with evaluator-only final scoring."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from a11y_benchmark.oracles.engine import evaluate
from a11y_benchmark.reset.engine import reset_case, variant_parameters
from a11y_benchmark.state_utils import stable_hash
from evaluation.config import CONFIGURATIONS, EvaluationConfiguration, TreatmentConfig
from evaluation.contracts import EvaluationResult, ExecutionOutcome, FailureClass, ManifestRun
from evaluation.storage import ResultStore


class RunExecutor(Protocol):
    def execute(self, run: ManifestRun, config: TreatmentConfig) -> ExecutionOutcome: ...


def effective_config_hash(config: TreatmentConfig, executor: RunExecutor | None = None) -> str:
    """Hash the treatment plus any executor-declared model/prompt fingerprint."""

    fingerprint_method = getattr(executor, "configuration_fingerprint", None)
    fingerprint = fingerprint_method(config) if callable(fingerprint_method) else None
    if not fingerprint:
        return config.config_hash
    canonical = json.dumps(
        {"treatment_hash": config.config_hash, "runtime": fingerprint},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_manifest(path: Path) -> list[ManifestRun]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    runs = TypeAdapter(list[ManifestRun]).validate_python(payload.get("runs"))
    if not runs:
        raise ValueError("Manifest tidak berisi run.")
    ids = [run.run_id for run in runs]
    if len(ids) != len(set(ids)):
        raise ValueError("Manifest memiliki run_id duplikat.")

    pairs: dict[str, list[ManifestRun]] = defaultdict(list)
    for run in runs:
        is_pilot_task = run.task_id.startswith("P")
        if (run.split == "pilot") != is_pilot_task:
            raise ValueError(f"Task dan split tidak cocok untuk {run.run_id}.")
        if (run.split == "pilot" and run.repetition != 0) or (
            run.split == "final" and run.repetition == 0
        ):
            raise ValueError(f"Repetition tidak cocok untuk split {run.run_id}.")
        expected = reset_case(run.task_id, run.condition_id, run.seed)
        expected_replay_key = (
            f"{run.task_id}:{run.condition_id}:{run.seed}:"
            f"{expected['snapshot_hash'][:12]}"
        )
        if run.replay_key != expected_replay_key:
            raise ValueError(f"replay_key tidak cocok untuk {run.run_id}.")
        expected_variant = stable_hash(variant_parameters(run.task_id, run.condition_id, run.seed))
        if run.variant_hash != expected_variant:
            raise ValueError(f"variant_hash tidak cocok untuk {run.run_id}.")
        pairs[run.pair_id].append(run)
    expected_configs = set(EvaluationConfiguration)
    for pair_id, members in pairs.items():
        if len(members) != 3:
            raise ValueError(f"Pair {pair_id} wajib memiliki tepat tiga run.")
        configs = {member.configuration for member in members}
        if configs != expected_configs:
            raise ValueError(f"Pair {pair_id} tidak memiliki tepat B0/B1/P.")
        if {member.order_position for member in members} != {1, 2, 3}:
            raise ValueError(f"Pair {pair_id} tidak memiliki order_position 1/2/3.")
        seeds = {member.seed for member in members}
        variants = {member.variant_hash for member in members}
        tasks = {member.task_id for member in members}
        conditions = {member.condition_id for member in members}
        splits = {member.split for member in members}
        if any(len(values) != 1 for values in (seeds, variants, tasks, conditions, splits)):
            raise ValueError(f"Pair {pair_id} tidak memakai seed/variant yang sama.")
    return runs


class EvaluationRunner:
    def __init__(
        self,
        *,
        executor: RunExecutor,
        store: ResultStore,
        infrastructure_retries: int = 1,
    ) -> None:
        if infrastructure_retries < 0 or infrastructure_retries > 3:
            raise ValueError("infrastructure_retries harus 0–3.")
        self.executor = executor
        self.store = store
        self.infrastructure_retries = infrastructure_retries

    def run(
        self,
        manifest: Iterable[ManifestRun],
        *,
        configurations: set[EvaluationConfiguration] | None = None,
        max_runs: int | None = None,
    ) -> list[EvaluationResult]:
        selected = [
            run for run in manifest if configurations is None or run.configuration in configurations
        ]
        if max_runs is not None:
            if max_runs < 1:
                raise ValueError("max_runs harus positif.")
            selected = selected[:max_runs]
        for configuration in {run.configuration for run in selected}:
            CONFIGURATIONS[configuration].require_ready()

        produced: list[EvaluationResult] = []
        for run in selected:
            previous = self.store.latest(run.run_id)
            config_hash = effective_config_hash(
                CONFIGURATIONS[run.configuration], self.executor
            )
            if (
                previous is not None
                and previous.resumable_complete
                and previous.config_hash == config_hash
            ):
                continue
            attempt = 1 if previous is None else previous.attempt + 1
            while True:
                result = self._execute_once(run, attempt)
                self.store.save(result)
                produced.append(result)
                if result.failure_class is not FailureClass.INFRASTRUCTURE:
                    break
                if attempt >= (1 if previous is None else previous.attempt + 1) + self.infrastructure_retries:
                    break
                attempt += 1
        return produced

    def _execute_once(self, run: ManifestRun, attempt: int) -> EvaluationResult:
        config = CONFIGURATIONS[run.configuration]
        try:
            outcome = self.executor.execute(run, config)
        except Exception as exc:  # Boundary: executor failures are infrastructure, not agent misses.
            outcome = ExecutionOutcome(
                terminal_reason="INFRASTRUCTURE_ERROR",
                error_code=type(exc).__name__,
                infrastructure_error=str(exc)[:2_000],
            )

        oracle = outcome.oracle_result
        if outcome.infrastructure_error is None and oracle is None and outcome.final_state is not None:
            oracle = evaluate(run.task_id, outcome.final_state)
        if oracle is not None and not all(
            isinstance(oracle.get(field), bool)
            for field in ("pass", "outcome_pass", "safety_pass")
        ):
            outcome = outcome.model_copy(
                update={
                    "infrastructure_error": "Hidden oracle mengembalikan kontrak tidak valid.",
                    "error_code": "ORACLE_RESULT_INVALID",
                }
            )
            oracle = None
        if outcome.infrastructure_error is not None or oracle is None:
            failure_class = FailureClass.INFRASTRUCTURE
        elif oracle and oracle["pass"]:
            failure_class = FailureClass.NONE
        else:
            failure_class = FailureClass.AGENT
        return EvaluationResult(
            run=run,
            config_hash=effective_config_hash(config, self.executor),
            attempt=attempt,
            agent_claimed_success=outcome.agent_claimed_success,
            oracle_success=oracle["pass"] if oracle else None,
            outcome_pass=oracle["outcome_pass"] if oracle else None,
            safety_pass=oracle["safety_pass"] if oracle else None,
            failure_class=failure_class,
            terminal_reason=outcome.terminal_reason,
            error_code=outcome.error_code,
            step_count=outcome.step_count,
            recovery_count=outcome.recovery_count,
            intervention_count=outcome.intervention_count,
            duration_ms=outcome.duration_ms,
            oracle=oracle,
            infrastructure_error=outcome.infrastructure_error,
            runtime_metadata=outcome.runtime_metadata,
        )


def validate_pilot_gate(
    store: ResultStore,
    pilot_manifest: Iterable[ManifestRun],
    *,
    executor: RunExecutor | None = None,
) -> None:
    """Block final-set access until every current-config pilot run is auditable."""

    missing: list[str] = []
    invalid: list[str] = []
    for run in pilot_manifest:
        result = store.latest(run.run_id)
        if result is None:
            missing.append(run.run_id)
            continue
        if result.failure_class is FailureClass.INFRASTRUCTURE:
            invalid.append(f"{run.run_id}:infrastructure")
        expected_hash = effective_config_hash(CONFIGURATIONS[run.configuration], executor)
        if result.config_hash != expected_hash:
            invalid.append(f"{run.run_id}:stale-config")
        required_metadata = ("model_id", "prompt_hash", "browser_version")
        if any(not result.runtime_metadata.get(field) for field in required_metadata):
            invalid.append(f"{run.run_id}:metadata")
    if missing or invalid:
        detail = ", ".join([*missing[:3], *invalid[:3]])
        raise RuntimeError(
            "Final manifest dikunci sampai 24 pilot current-config selesai tanpa kegagalan "
            f"infrastruktur dan metadata lengkap. Contoh gap: {detail or 'unknown'}"
        )
