#!/usr/bin/env python3
"""Generate Stage 3 artifacts from the versioned Python catalog."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from a11y_benchmark import STAGE3_VERSION  # noqa: E402
from a11y_benchmark.catalog import (  # noqa: E402
    CONDITIONS,
    FINAL_TASKS,
    HANDOFF_ORACLES,
    INTERFACE_CONDITIONS,
    PILOT_TASKS,
    USER_STUDY_TASK_IDS,
    private_task,
    public_task,
)
from a11y_benchmark.manifests import build_final_runs, build_pilot_runs, final_seed  # noqa: E402
from a11y_benchmark.reset.engine import reset_case  # noqa: E402
from a11y_benchmark.state_utils import stable_hash  # noqa: E402

PUBLIC = ROOT / "benchmark" / "public"
PRIVATE = ROOT / "benchmark" / "private"
SCHEMAS = ROOT / "benchmark" / "schemas"
FIXTURES = ROOT / "benchmark" / "fixtures"
RESET = ROOT / "benchmark" / "reset"
DOCS = ROOT / "docs"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def task_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/a11y-cua/task-spec.schema.json",
        "title": "Public benchmark task specification",
        "type": "object",
        "required": [
            "id", "domain", "name", "goal", "start_route", "allowed_actions",
            "forbidden_actions", "max_steps", "completion_boundary",
            "keyboard_path", "data_policy", "conditions", "reset_contract",
            "collaboration_contract",
        ],
        "properties": {
            "id": {"type": "string", "pattern": "^[TP][0-9]{2}$"},
            "domain": {"enum": ["travel", "marketplace", "appointment", "account"]},
            "name": {"type": "string", "minLength": 3},
            "goal": {"type": "string", "minLength": 20},
            "start_route": {"type": "string", "pattern": "^/"},
            "allowed_actions": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "forbidden_actions": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "max_steps": {"type": "integer", "minimum": 1, "maximum": 30},
            "completion_boundary": {"type": "string", "minLength": 10},
            "keyboard_path": {"type": "array", "minItems": 2, "items": {"type": "string"}},
            "data_policy": {"const": "synthetic_only"},
            "risk": {"enum": ["LOW", "MEDIUM", "HIGH"]},
            "conditions": {"type": "array", "const": ["C0", "C1", "C2"]},
            "reset_contract": {"type": "object"},
            "collaboration_contract": {
                "type": "object",
                "required": [
                    "task_map_required", "completed_claim_policy",
                    "relevant_item_grounding", "stale_entries_invalidated",
                    "takeover_supported", "resume_requires_fresh_observation",
                    "focus_handoff_required_for_study",
                ],
                "properties": {
                    "task_map_required": {"const": True},
                    "completed_claim_policy": {"const": "VERIFIED_ONLY"},
                    "relevant_item_grounding": {"const": "LATEST_AX_SNAPSHOT"},
                    "stale_entries_invalidated": {"const": True},
                    "takeover_supported": {"const": True},
                    "resume_requires_fresh_observation": {"const": True},
                    "focus_handoff_required_for_study": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def condition_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/a11y-cua/condition.schema.json",
        "title": "Benchmark condition",
        "type": "object",
        "required": ["id", "name", "capability", "description", "required_properties", "fairness_constraints"],
        "properties": {
            "id": {"enum": ["C0", "C1", "C2"]},
            "name": {"type": "string"},
            "capability": {"type": "string"},
            "description": {"type": "string"},
            "required_properties": {"type": "array", "minItems": 3, "items": {"type": "string"}},
            "fairness_constraints": {"type": "array", "minItems": 2, "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }


def interface_condition_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/a11y-cua/interface-condition.schema.json",
        "title": "User-facing interface condition",
        "type": "object",
        "required": [
            "id", "name", "description", "core_agent", "task_map",
            "verified_progress_evidence", "focus_synchronized_handoff",
            "controls", "fairness_constraints",
        ],
        "properties": {
            "id": {"enum": ["U0", "U1"]},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "core_agent": {"const": "identical"},
            "task_map": {"type": "boolean"},
            "verified_progress_evidence": {"type": "boolean"},
            "focus_synchronized_handoff": {"type": "boolean"},
            "controls": {"type": "array", "minItems": 6, "items": {"type": "string"}},
            "fairness_constraints": {"type": "array", "minItems": 2, "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }


def task_map_snapshot_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.invalid/a11y-cua/task-map-snapshot.schema.json",
        "title": "Shared Accessible Task View snapshot",
        "type": "object",
        "required": [
            "session_id", "snapshot_version", "goal", "constraints", "progress",
            "verified_completed_steps", "relevant_items", "next_action", "control_state",
        ],
        "properties": {
            "session_id": {"type": "string"},
            "snapshot_version": {"type": "integer", "minimum": 1},
            "goal": {"type": "string"},
            "constraints": {"type": "array", "items": {"type": "string"}},
            "progress": {"type": "string"},
            "verified_completed_steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["label", "verification_status", "evidence_ref"],
                    "properties": {
                        "label": {"type": "string"},
                        "verification_status": {"const": "VERIFIED"},
                        "evidence_ref": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "relevant_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["semantic_ref", "role", "name", "snapshot_version"],
                    "properties": {
                        "semantic_ref": {"type": "string"},
                        "role": {"type": "string"},
                        "name": {"type": "string"},
                        "snapshot_version": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
            },
            "next_action": {
                "type": "object",
                "required": ["label", "status"],
                "properties": {
                    "label": {"type": "string"},
                    "status": {"const": "PLANNED_NOT_COMPLETED"},
                },
                "additionalProperties": False,
            },
            "control_state": {
                "type": "object",
                "required": ["agent_paused", "takeover_lock", "available_controls"],
                "properties": {
                    "agent_paused": {"type": "boolean"},
                    "takeover_lock": {"type": "boolean"},
                    "available_controls": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def build_user_study_plan() -> dict:
    return {
        "design": "within_subject_counterbalanced",
        "target_participants": {"minimum": 6, "maximum": 8},
        "inclusion": "Adult blind users who regularly use a desktop screen reader.",
        "conditions": ["U0", "U1"],
        "task_ids": USER_STUDY_TASK_IDS,
        "tasks_per_participant": 4,
        "session_minutes": {"minimum": 45, "maximum": 60},
        "burden_controls": [
            "One short practice task before measurement.",
            "Break offered between task pairs.",
            "Pause or withdraw at any time without penalty.",
            "Synthetic data only; no credential, payment, or real transaction.",
            "The system is being tested, not the participant.",
        ],
        "measures": [
            "handoff_to_relevant_focus_time",
            "navigation_keystrokes_after_takeover",
            "continuation_success_without_reset",
            "facilitator_help_requests",
            "task_completion",
            "short_ease_and_control_ratings",
            "brief_semistructured_feedback",
        ],
        "input_policy": "Participant may choose text or push-to-talk; keep the choice constant across U0/U1.",
        "substitution_policy": "Do not substitute sighted blindfolded participants for blind screen-reader users.",
    }


def build_case_matrix() -> list[dict]:
    cases = []
    for task in FINAL_TASKS:
        for condition_id in ("C0", "C1", "C2"):
            cases.append(
                {
                    "case_id": f"{task['id']}-{condition_id}",
                    "task_id": task["id"],
                    "domain": task["domain"],
                    "condition_id": condition_id,
                    "goal_ref": task["id"],
                    "start_route": task["start_route"],
                    "max_steps": task["max_steps"],
                    "challenge_family": task["condition_challenges"][condition_id],
                    "keyboard_path_declared": True,
                    "safe_path_declared": True,
                    "collaboration_contract_declared": True,
                    "implementation_status": "READY_FOR_STAGE_5",
                }
            )
    return cases


def build_reference_resets() -> list[dict]:
    payloads = []
    for task in FINAL_TASKS:
        for condition_id in ("C0", "C1", "C2"):
            seed = final_seed(task["id"], condition_id, 1)
            payloads.append(reset_case(task["id"], condition_id, seed))
    return payloads


def build_reset_material(tasks: list[dict]) -> list[dict]:
    """Data available to the benchmark server, excluding any scoring truth."""
    return [
        {
            "id": task["id"],
            "records": task["records"],
            "initial_state": task["initial_state"],
            "condition_challenges": task["condition_challenges"],
        }
        for task in tasks
    ]


def build_design_markdown(cases: list[dict], final_runs: list[dict], pilot_runs: list[dict]) -> str:
    lines = [
        "# Tahap 3 — Benchmark and Hidden-Oracle Design",
        "",
        f"Version: `{STAGE3_VERSION}`  ",
        "Status: **COMPLETE IN DESIGN / READY FOR STAGE 4–5 IMPLEMENTATION**",
        "",
        "## Locked experiment size",
        "",
        f"- Final tasks: {len(FINAL_TASKS)}",
        f"- Conditions: {len(CONDITIONS)}",
        f"- Task-condition cases: {len(cases)}",
        f"- Final run rows: {len(final_runs)}",
        f"- Pilot run rows: {len(pilot_runs)}",
        f"- User-facing interface conditions: {len(INTERFACE_CONDITIONS)} (U0/U1)",
        f"- Participant-study task subset: {len(USER_STUDY_TASK_IDS)}",
        "- Final unit of analysis: 36 task-condition cases; repetitions are nested.",
        "",
        "## Public/private boundary",
        "",
        "The runner may mount `benchmark/public/` and the selected reset payload. It must not mount ",
        "`benchmark/private/`, `a11y_benchmark/oracles/`, or validation fixtures. The planner receives ",
        "only the public goal and browser observation. Final success comes from the deterministic ",
        "oracle after the run; the runtime verifier is a different component.",
        "",
        "## Final task catalog",
        "",
        "| ID | Domain | Task | Max steps | Boundary |",
        "|---|---|---|---:|---|",
    ]
    for task in FINAL_TASKS:
        lines.append(
            f"| {task['id']} | {task['domain']} | {task['name']} | {task['max_steps']} | {task['completion_boundary']} |"
        )
    lines.extend(
        [
            "",
            "## Condition intent",
            "",
            "| ID | Capability | Fairness summary |",
            "|---|---|---|",
        ]
    )
    for condition_id, condition in CONDITIONS.items():
        lines.append(
            f"| {condition_id} | {condition['capability']} | {condition['fairness_constraints'][0]} |"
        )
    lines.extend(
        [
            "",
            "## Claim boundary",
            "",
            "Tahap 3 validates specification completeness, deterministic reset, oracle behavior, ",
            "split integrity, and leakage prevention. It does **not** validate rendered keyboard ",
            "operation, task-map runtime fidelity, focus handoff with NVDA, participant usability, or mini-site ",
            "accessibility; those require the later web artifact and user study. The original 324-run benchmark ",
            "remains intact; U0/U1 is a separate, participant-facing comparison.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    final_public = [public_task(task) for task in FINAL_TASKS]
    pilot_public = [public_task(task) for task in PILOT_TASKS]
    conditions = [{"id": key, **value} for key, value in CONDITIONS.items()]
    cases = build_case_matrix()
    final_runs = build_final_runs()
    pilot_runs = build_pilot_runs()
    reference_resets = build_reference_resets()

    write_json(PUBLIC / "task_specs.json", {"version": STAGE3_VERSION, "tasks": final_public})
    write_json(PUBLIC / "pilot_task_specs.json", {"version": STAGE3_VERSION, "tasks": pilot_public})
    write_json(PUBLIC / "conditions.json", {"version": STAGE3_VERSION, "conditions": conditions})
    write_json(PUBLIC / "case_matrix.json", {"version": STAGE3_VERSION, "cases": cases})
    write_json(
        PUBLIC / "interface_conditions.json",
        {
            "version": STAGE3_VERSION,
            "interfaces": [{"id": key, **value} for key, value in INTERFACE_CONDITIONS.items()],
        },
    )
    write_json(PUBLIC / "user_study_plan.json", {"version": STAGE3_VERSION, **build_user_study_plan()})

    write_json(PRIVATE / "task_oracles.json", {"version": STAGE3_VERSION, "tasks": [private_task(t) for t in FINAL_TASKS]})
    write_json(PRIVATE / "pilot_task_oracles.json", {"version": STAGE3_VERSION, "tasks": [private_task(t) for t in PILOT_TASKS]})
    write_json(
        PRIVATE / "collaboration_oracles.json",
        {
            "version": STAGE3_VERSION,
            "tasks": [
                {
                    "id": task["id"],
                    "handoff_oracle": HANDOFF_ORACLES[task["id"]],
                    "verified_completion_predicates": task["predicates"],
                    "safety_invariants": task["invariants"],
                }
                for task in FINAL_TASKS
                if task["id"] in USER_STUDY_TASK_IDS
            ],
        },
    )
    write_json(PRIVATE / "manifests" / "final_runs.json", {"version": STAGE3_VERSION, "runs": final_runs})
    write_json(PRIVATE / "manifests" / "pilot_runs.json", {"version": STAGE3_VERSION, "runs": pilot_runs})

    write_json(
        RESET / "reset_material.json",
        {"version": STAGE3_VERSION, "tasks": build_reset_material(FINAL_TASKS + PILOT_TASKS)},
    )
    write_json(FIXTURES / "reference_reset_payloads.json", {"version": STAGE3_VERSION, "payloads": reference_resets})
    write_json(SCHEMAS / "task_spec.schema.json", task_schema())
    write_json(SCHEMAS / "condition.schema.json", condition_schema())
    write_json(SCHEMAS / "interface_condition.schema.json", interface_condition_schema())
    write_json(SCHEMAS / "task_map_snapshot.schema.json", task_map_snapshot_schema())
    write_json(
        ROOT / "benchmark" / "build_manifest.json",
        {
            "version": STAGE3_VERSION,
            "catalog_hash": stable_hash({"tasks": FINAL_TASKS, "conditions": CONDITIONS}),
            "counts": {
                "tasks": 12,
                "conditions": 3,
                "cases": 36,
                "final_runs": 324,
                "pilot_runs": 24,
                "interface_conditions": 2,
                "user_study_tasks": 4,
            },
            "split_policy": "pilot task IDs and seeds are disjoint from final",
            "oracle_policy": "deterministic; hidden from agent; no LLM judge",
        },
    )
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "benchmark_design.md").write_text(
        build_design_markdown(cases, final_runs, pilot_runs), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "version": STAGE3_VERSION,
                "tasks": len(final_public),
                "cases": len(cases),
                "final_runs": len(final_runs),
                "pilot_runs": len(pilot_runs),
                "interface_conditions": len(INTERFACE_CONDITIONS),
                "user_study_tasks": len(USER_STUDY_TASK_IDS),
            }
        )
    )


if __name__ == "__main__":
    main()
