"""Machine-readable run export and compact aggregate tables."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from a11y_benchmark.catalog import get_task
from evaluation.contracts import EvaluationResult, FailureClass


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * total)) / total) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def latest_attempts(results: list[EvaluationResult]) -> list[EvaluationResult]:
    latest: dict[str, EvaluationResult] = {}
    for result in results:
        current = latest.get(result.run.run_id)
        if current is None or result.attempt > current.attempt:
            latest[result.run.run_id] = result
    return sorted(latest.values(), key=lambda item: item.run.run_id)


def _aggregate(
    latest: list[EvaluationResult],
    *,
    dimensions: tuple[str, ...],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[EvaluationResult]] = defaultdict(list)
    for result in latest:
        values = {
            "configuration": result.run.configuration.value,
            "condition_id": result.run.condition_id,
            "task_id": result.run.task_id,
            "domain": get_task(result.run.task_id)["domain"],
            "error_code": result.error_code,
        }
        grouped[tuple(str(values[dimension]) for dimension in dimensions)].append(result)
    rows = []
    for keys, members in sorted(grouped.items()):
        analyzable = [item for item in members if item.failure_class is not FailureClass.INFRASTRUCTURE]
        successes = sum(item.oracle_success is True for item in analyzable)
        low, high = _wilson(successes, len(analyzable))
        rows.append(
            {
                **dict(zip(dimensions, keys, strict=True)),
                "scheduled_runs": len(members),
                "analyzable_runs": len(analyzable),
                "infrastructure_failures": len(members) - len(analyzable),
                "oracle_successes": successes,
                "success_rate": successes / len(analyzable) if analyzable else None,
                "wilson_95_low": low if analyzable else None,
                "wilson_95_high": high if analyzable else None,
                "mean_duration_ms": (
                    sum(item.duration_ms for item in analyzable) / len(analyzable)
                    if analyzable
                    else None
                ),
                "mean_steps": (
                    sum(item.step_count for item in analyzable) / len(analyzable)
                    if analyzable
                    else None
                ),
                "mean_recoveries": (
                    sum(item.recovery_count for item in analyzable) / len(analyzable)
                    if analyzable
                    else None
                ),
                "mean_interventions": (
                    sum(item.intervention_count for item in analyzable) / len(analyzable)
                    if analyzable
                    else None
                ),
            }
        )
    return rows


def _mcnemar_exact(left_only: int, right_only: int) -> float | None:
    discordant = left_only + right_only
    if discordant == 0:
        return None
    tail = sum(math.comb(discordant, value) for value in range(min(left_only, right_only) + 1))
    return min(1.0, 2 * tail / (2**discordant))


def _paired_comparisons(latest: list[EvaluationResult]) -> list[dict[str, Any]]:
    by_pair: dict[str, dict[str, EvaluationResult]] = defaultdict(dict)
    for result in latest:
        if result.failure_class is not FailureClass.INFRASTRUCTURE:
            by_pair[result.run.pair_id][result.run.configuration.value] = result
    rows = []
    for left, right in (("B0", "B1"), ("B0", "P"), ("B1", "P")):
        pairs = [members for members in by_pair.values() if left in members and right in members]
        left_only = sum(
            members[left].oracle_success is True and members[right].oracle_success is not True
            for members in pairs
        )
        right_only = sum(
            members[right].oracle_success is True and members[left].oracle_success is not True
            for members in pairs
        )
        both = sum(
            members[left].oracle_success is True and members[right].oracle_success is True
            for members in pairs
        )
        neither = len(pairs) - left_only - right_only - both
        left_rate = sum(members[left].oracle_success is True for members in pairs) / len(pairs) if pairs else None
        right_rate = sum(members[right].oracle_success is True for members in pairs) / len(pairs) if pairs else None
        rows.append(
            {
                "left": left,
                "right": right,
                "complete_pairs": len(pairs),
                "both_success": both,
                "left_only_success": left_only,
                "right_only_success": right_only,
                "neither_success": neither,
                "success_rate_delta_right_minus_left": (
                    right_rate - left_rate if left_rate is not None and right_rate is not None else None
                ),
                "mcnemar_exact_p": _mcnemar_exact(left_only, right_only),
            }
        )
    return rows


def build_summary(results: list[EvaluationResult]) -> dict[str, Any]:
    latest = latest_attempts(results)
    primary = _aggregate(latest, dimensions=("configuration", "condition_id"))
    return {
        "schema_version": "evaluation-summary-v1",
        "attempt_records": len(results),
        "latest_runs": len(latest),
        "infrastructure_failures": sum(
            item.failure_class is FailureClass.INFRASTRUCTURE for item in latest
        ),
        "agent_claim_oracle_mismatches": sum(
            item.oracle_success is not None and item.agent_claimed_success != item.oracle_success
            for item in latest
        ),
        "safety_failures": sum(item.safety_pass is False for item in latest),
        "groups": primary,
        "by_configuration": _aggregate(latest, dimensions=("configuration",)),
        "by_task": _aggregate(latest, dimensions=("configuration", "task_id")),
        "by_domain": _aggregate(latest, dimensions=("configuration", "domain")),
        "by_error": _aggregate(latest, dimensions=("configuration", "error_code")),
        "paired_comparisons": _paired_comparisons(latest),
    }


def write_reports(results: list[EvaluationResult], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    latest = latest_attempts(results)
    run_json = output_dir / "runs.json"
    run_csv = output_dir / "runs.csv"
    summary_json = output_dir / "summary.json"
    summary_csv = output_dir / "summary.csv"
    run_json.write_text(
        json.dumps([item.model_dump(mode="json") for item in latest], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    run_rows = [
        {
            "run_id": item.run.run_id,
            "split": item.run.split,
            "task_id": item.run.task_id,
            "domain": get_task(item.run.task_id)["domain"],
            "condition_id": item.run.condition_id,
            "configuration": item.run.configuration.value,
            "pair_id": item.run.pair_id,
            "seed": item.run.seed,
            "attempt": item.attempt,
            "config_hash": item.config_hash,
            "oracle_success": item.oracle_success,
            "outcome_pass": item.outcome_pass,
            "safety_pass": item.safety_pass,
            "agent_claimed_success": item.agent_claimed_success,
            "failure_class": item.failure_class.value,
            "terminal_reason": item.terminal_reason,
            "error_code": item.error_code,
            "duration_ms": item.duration_ms,
            "step_count": item.step_count,
            "recovery_count": item.recovery_count,
            "intervention_count": item.intervention_count,
            "model_id": item.runtime_metadata.get("model_id"),
            "prompt_version": item.runtime_metadata.get("prompt_version"),
            "prompt_hash": item.runtime_metadata.get("prompt_hash"),
            "browser_version": item.runtime_metadata.get("browser_version"),
        }
        for item in latest
    ]
    _write_csv(run_csv, run_rows)
    summary = build_summary(results)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(summary_csv, summary["groups"])
    return {
        "runs_json": run_json,
        "runs_csv": run_csv,
        "summary_json": summary_json,
        "summary_csv": summary_csv,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
