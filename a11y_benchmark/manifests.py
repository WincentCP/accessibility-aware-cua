"""Frozen split and paired-run manifest generation."""

from __future__ import annotations

from a11y_benchmark.catalog import CONFIGURATIONS, FINAL_TASKS, PILOT_TASKS
from a11y_benchmark.reset.engine import replay_key, variant_parameters
from a11y_benchmark.state_utils import stable_hash, stable_int

LATIN_ORDERS = [
    ["B0", "B1", "P"],
    ["B1", "P", "B0"],
    ["P", "B0", "B1"],
]


def final_seed(task_id: str, condition_id: str, repetition: int) -> int:
    return 300_000_000 + stable_int(f"final-v1|{task_id}|{condition_id}|{repetition}", 8)


def pilot_seed(task_id: str, condition_id: str) -> int:
    return 900_000_000 + stable_int(f"pilot-v1|{task_id}|{condition_id}", 8)


def build_final_runs() -> list[dict]:
    runs = []
    for task in FINAL_TASKS:
        for condition_id in ("C0", "C1", "C2"):
            for repetition in (1, 2, 3):
                seed = final_seed(task["id"], condition_id, repetition)
                variant = variant_parameters(task["id"], condition_id, seed)
                order = LATIN_ORDERS[repetition - 1]
                pair_id = f"{task['id']}-{condition_id}-R{repetition}"
                for position, configuration in enumerate(order, start=1):
                    runs.append(
                        {
                            "run_id": f"FINAL-{pair_id}-{configuration}",
                            "split": "final",
                            "task_id": task["id"],
                            "condition_id": condition_id,
                            "repetition": repetition,
                            "configuration": configuration,
                            "order_position": position,
                            "pair_id": pair_id,
                            "seed": seed,
                            "variant_hash": stable_hash(variant),
                            "replay_key": replay_key(task["id"], condition_id, seed),
                        }
                    )
    return runs

PILOT_CONDITION_PAIRS = {
    "P01": ["C0", "C1"],
    "P02": ["C1", "C2"],
    "P03": ["C0", "C2"],
    "P04": ["C1", "C2"],
}


def build_pilot_runs() -> list[dict]:
    runs = []
    for task in PILOT_TASKS:
        for condition_id in PILOT_CONDITION_PAIRS[task["id"]]:
            seed = pilot_seed(task["id"], condition_id)
            variant = variant_parameters(task["id"], condition_id, seed)
            pair_id = f"{task['id']}-{condition_id}-PILOT"
            for position, configuration in enumerate(CONFIGURATIONS, start=1):
                runs.append(
                    {
                        "run_id": f"PILOT-{task['id']}-{condition_id}-{configuration}",
                        "split": "pilot",
                        "task_id": task["id"],
                        "condition_id": condition_id,
                        "repetition": 0,
                        "configuration": configuration,
                        "order_position": position,
                        "pair_id": pair_id,
                        "seed": seed,
                        "variant_hash": stable_hash(variant),
                        "replay_key": replay_key(task["id"], condition_id, seed),
                    }
                )
    return runs
