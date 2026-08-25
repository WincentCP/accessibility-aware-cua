"""Pure reset function used by the future mini-sites and evaluation runner.

The output deliberately excludes hidden predicates, success patches, target
annotations, and near-miss fixtures. The same input tuple always produces an
identical output and snapshot hash.
"""

from __future__ import annotations

import random
from copy import deepcopy

from a11y_benchmark.catalog import CONDITIONS, get_task, public_task
from a11y_benchmark.state_utils import stable_hash

LABEL_VARIANTS = {
    "C0": ["default"],
    "C1": ["equivalent-a", "equivalent-b", "equivalent-c"],
    "C2": ["default"],
}


def variant_parameters(task_id: str, condition_id: str, seed: int) -> dict:
    if condition_id not in CONDITIONS:
        raise ValueError(f"Unknown condition_id: {condition_id}")
    rng = random.Random(f"stage3|{task_id}|{condition_id}|{seed}")
    label_variant = rng.choice(LABEL_VARIANTS[condition_id])
    delay_ms = rng.choice([450, 650, 850, 1050]) if condition_id == "C2" else 0
    return {
        "label_variant": label_variant,
        "layout_variant": "reflowed" if condition_id == "C1" else "standard",
        "visual_order_offset": rng.randrange(1, 4) if condition_id == "C1" else 0,
        # One offset is applied consistently within a case so ordering and the
        # logically correct option remain unchanged. These values are hidden
        # from the planner manifest but visible naturally through rendered data.
        "price_offset": rng.choice([-15_000, -10_000, 0, 10_000, 15_000]),
        "time_offset_minutes": rng.choice([-10, -5, 0, 5, 10])
        if task_id in {"T01", "T02", "T07", "P01"}
        else 0,
        "delay_ms": delay_ms,
        "rerender_once": condition_id == "C2",
        "challenge_family": get_task(task_id)["condition_challenges"][condition_id],
    }


def _shift_hhmm(value: str, minutes: int) -> str:
    hour, minute = (int(part) for part in value.split(":"))
    total = hour * 60 + minute + minutes
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def _apply_visible_variants(records: list[dict], variant: dict) -> list[dict]:
    updated = deepcopy(records)
    for record in updated:
        if "price" in record:
            record["price"] += variant["price_offset"]
        for key in ("depart", "arrive", "time"):
            if key in record and variant["time_offset_minutes"]:
                record[key] = _shift_hhmm(record[key], variant["time_offset_minutes"])
    return updated


def reset_case(task_id: str, condition_id: str, seed: int) -> dict:
    task = get_task(task_id)
    if condition_id not in CONDITIONS:
        raise ValueError(f"Unknown condition_id: {condition_id}")

    rng = random.Random(f"records|{task_id}|{condition_id}|{seed}")
    variant = variant_parameters(task_id, condition_id, seed)
    records = _apply_visible_variants(task["records"], variant)
    rng.shuffle(records)

    state = deepcopy(task["initial_state"])
    state["_meta"] = {
        "task_id": task_id,
        "condition_id": condition_id,
        "seed": seed,
        "synthetic": True,
        "reset_version": "stage3-v1",
    }
    public_fixture = {
        "task": public_task(task),
        "condition": {
            "id": condition_id,
            "name": CONDITIONS[condition_id]["name"],
        },
        "records": records,
        "presentation": variant,
    }
    payload = {"public_fixture": public_fixture, "state": state}
    payload["snapshot_hash"] = stable_hash(payload)
    return payload


def replay_key(task_id: str, condition_id: str, seed: int) -> str:
    payload = reset_case(task_id, condition_id, seed)
    return f"{task_id}:{condition_id}:{seed}:{payload['snapshot_hash'][:12]}"
