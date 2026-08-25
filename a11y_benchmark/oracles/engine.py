"""Deterministic final-state oracle without LLM judgement."""

from __future__ import annotations

from typing import Any

from a11y_benchmark.catalog import get_task
from a11y_benchmark.reset.engine import reset_case
from a11y_benchmark.state_utils import MISSING, apply_patch, get_path


def _check(predicate: dict, state: dict) -> dict:
    path = predicate["path"]
    actual = get_path(state, path, MISSING)
    expected = predicate.get("value")
    op = predicate["op"]

    if actual is MISSING:
        passed = False
        rendered_actual: Any = "__MISSING__"
    else:
        rendered_actual = actual
        if op == "eq":
            passed = actual == expected
        elif op == "neq":
            passed = actual != expected
        elif op == "true":
            passed = actual is True
        elif op == "false":
            passed = actual is False
        elif op == "gte":
            passed = actual >= expected
        elif op == "lte":
            passed = actual <= expected
        elif op == "contains":
            passed = expected in actual
        elif op == "subset":
            passed = set(expected).issubset(set(actual))
        elif op == "between":
            passed = expected[0] <= actual <= expected[1]
        else:
            raise ValueError(f"Unsupported oracle op: {op}")

    return {
        "path": path,
        "op": op,
        "expected": expected,
        "actual": rendered_actual,
        "passed": passed,
        "safety": predicate.get("safety"),
    }


def evaluate(task_id: str, state: dict) -> dict:
    task = get_task(task_id)
    outcome_checks = [_check(p, state) for p in task["predicates"]]
    invariant_checks = [_check(p, state) for p in task["invariants"]]
    outcome_pass = all(item["passed"] for item in outcome_checks)
    safety_pass = all(item["passed"] for item in invariant_checks)
    return {
        "task_id": task_id,
        "oracle_version": "stage3-v1",
        "pass": outcome_pass and safety_pass,
        "outcome_pass": outcome_pass,
        "safety_pass": safety_pass,
        "checks": outcome_checks,
        "invariants": invariant_checks,
    }


def success_state(task_id: str, condition_id: str, seed: int) -> dict:
    task = get_task(task_id)
    state = reset_case(task_id, condition_id, seed)["state"]
    return apply_patch(state, task["success_patch"])


def near_miss_states(task_id: str, condition_id: str, seed: int) -> list[dict]:
    task = get_task(task_id)
    correct = success_state(task_id, condition_id, seed)
    result = []
    for miss in task["near_misses"]:
        result.append(
            {
                "id": miss["id"],
                "reason": miss["reason"],
                "state": apply_patch(correct, miss["patch"]),
            }
        )
    return result
