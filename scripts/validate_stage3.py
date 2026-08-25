#!/usr/bin/env python3
"""Validate Stage 3 and write an auditable 36-case report."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from a11y_benchmark import STAGE3_VERSION  # noqa: E402
from a11y_benchmark.catalog import (  # noqa: E402
    CONDITIONS,
    FINAL_TASKS,
    HANDOFF_ORACLES,
    INTERFACE_CONDITIONS,
    USER_STUDY_TASK_IDS,
    public_task,
)
from a11y_benchmark.manifests import (  # noqa: E402
    LATIN_ORDERS,
    build_final_runs,
    build_pilot_runs,
    final_seed,
)
from a11y_benchmark.oracles.engine import evaluate, near_miss_states, success_state  # noqa: E402
from a11y_benchmark.reset.engine import reset_case  # noqa: E402

REPORT_DIR = ROOT / "reports"
FORBIDDEN_PUBLIC_KEYS = {
    "initial_state", "success_patch", "predicates", "invariants", "near_misses",
    "expected_final_state", "target_id", "oracle",
    "handoff_oracle", "handoff_trigger", "focus_target", "context_record_id",
}


def nested_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from nested_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from nested_keys(nested)


def public_leaks() -> list[dict]:
    leaks = []
    for path in sorted((ROOT / "benchmark" / "public").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        hits = sorted(set(nested_keys(value)) & FORBIDDEN_PUBLIC_KEYS)
        if hits:
            leaks.append({"file": path.name, "keys": hits})
    return leaks


def reset_scoring_leaks() -> list[str]:
    value = json.loads(
        (ROOT / "benchmark" / "reset" / "reset_material.json").read_text(encoding="utf-8")
    )
    scoring_keys = {
        "success_patch", "predicates", "invariants", "near_misses",
        "expected_final_state", "target_id", "oracle",
    }
    return sorted(set(nested_keys(value)) & scoring_keys)


def validate_case(task: dict, condition_id: str) -> dict:
    seed = final_seed(task["id"], condition_id, 1)
    first = reset_case(task["id"], condition_id, seed)
    second = reset_case(task["id"], condition_id, seed)
    correct = success_state(task["id"], condition_id, seed)
    correct_result = evaluate(task["id"], correct)
    misses = near_miss_states(task["id"], condition_id, seed)
    miss_results = [evaluate(task["id"], miss["state"])["pass"] for miss in misses]
    collaboration = public_task(task)["collaboration_contract"]
    checks = {
        "reset_idempotent": first == second,
        "reset_hash_stable": first["snapshot_hash"] == second["snapshot_hash"],
        "success_state_passes": correct_result["pass"],
        "three_near_misses_declared": len(misses) >= 3,
        "all_near_misses_fail": not any(miss_results),
        "keyboard_path_declared": len(task["keyboard_path"]) >= 2,
        "max_steps_bounded": 0 < task["max_steps"] <= 30,
        "safe_boundary_declared": bool(task["forbidden_actions"] and task["completion_boundary"]),
        "synthetic_only": task["data_policy"] == "synthetic_only",
        "verified_task_map_contract": (
            collaboration["completed_claim_policy"] == "VERIFIED_ONLY"
            and collaboration["relevant_item_grounding"] == "LATEST_AX_SNAPSHOT"
            and collaboration["stale_entries_invalidated"]
            and collaboration["resume_requires_fresh_observation"]
        ),
    }
    return {
        "case_id": f"{task['id']}-{condition_id}",
        "task_id": task["id"],
        "domain": task["domain"],
        "condition_id": condition_id,
        "seed_for_qa": seed,
        "snapshot_hash": first["snapshot_hash"],
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "browser_keyboard_walkthrough": "PENDING_STAGE_5",
        "nvda_walkthrough": "PENDING_STAGE_5_12",
    }


def validate_manifest(final_runs: list[dict], pilot_runs: list[dict]) -> dict:
    paired = defaultdict(list)
    for run in final_runs:
        paired[run["pair_id"]].append(run)
    pair_ok = all(
        len(group) == 3
        and {r["configuration"] for r in group} == {"B0", "B1", "P"}
        and len({r["seed"] for r in group}) == 1
        and len({r["variant_hash"] for r in group}) == 1
        and [r["configuration"] for r in sorted(group, key=lambda x: x["order_position"])]
        == LATIN_ORDERS[group[0]["repetition"] - 1]
        for group in paired.values()
    )
    return {
        "final_runs_324": len(final_runs) == 324,
        "final_pair_groups_108": len(paired) == 108,
        "paired_seed_variant_and_latin_order": pair_ok,
        "pilot_runs_24": len(pilot_runs) == 24,
        "pilot_task_ids_disjoint": {r["task_id"] for r in pilot_runs}.isdisjoint(
            {r["task_id"] for r in final_runs}
        ),
        "pilot_seeds_disjoint": {r["seed"] for r in pilot_runs}.isdisjoint(
            {r["seed"] for r in final_runs}
        ),
    }


def validate_collaboration_contracts() -> dict:
    u0 = INTERFACE_CONDITIONS["U0"]
    u1 = INTERFACE_CONDITIONS["U1"]
    schema = json.loads(
        (ROOT / "benchmark" / "schemas" / "task_map_snapshot.schema.json").read_text(encoding="utf-8")
    )
    study = json.loads(
        (ROOT / "benchmark" / "public" / "user_study_plan.json").read_text(encoding="utf-8")
    )
    completed = schema["properties"]["verified_completed_steps"]["items"]["properties"]
    next_action = schema["properties"]["next_action"]["properties"]
    return {
        "two_interface_conditions_u0_u1": set(INTERFACE_CONDITIONS) == {"U0", "U1"},
        "interface_core_agent_identical": u0["core_agent"] == u1["core_agent"] == "identical",
        "treatment_is_task_map_and_focus_handoff": (
            not u0["task_map"]
            and not u0["focus_synchronized_handoff"]
            and u1["task_map"]
            and u1["verified_progress_evidence"]
            and u1["focus_synchronized_handoff"]
        ),
        "four_user_study_tasks": len(USER_STUDY_TASK_IDS) == 4,
        "handoff_oracles_complete": set(HANDOFF_ORACLES) == set(USER_STUDY_TASK_IDS),
        "task_map_completed_claims_verified_only": completed["verification_status"]["const"] == "VERIFIED",
        "task_map_next_action_not_mislabeled_complete": next_action["status"]["const"] == "PLANNED_NOT_COMPLETED",
        "participant_burden_bounded": (
            study["tasks_per_participant"] == 4
            and study["session_minutes"] == {"minimum": 45, "maximum": 60}
            and study["target_participants"] == {"minimum": 6, "maximum": 8}
        ),
        "no_blindfolded_substitution": "Do not substitute sighted blindfolded" in study["substitution_policy"],
    }


def markdown(report: dict) -> str:
    lines = [
        "# Benchmark Validation Report — Tahap 3",
        "",
        f"- Version: `{report['version']}`",
        f"- Validation date: {report['validation_date']}",
        f"- Overall design status: **{report['overall_status']}**",
        f"- Cases passing spec/reset/oracle checks: **{report['summary']['cases_passed']}/36**",
        f"- Near-miss evaluations rejected: **{report['summary']['near_miss_rejections']}/108**",
        f"- Public leakage findings: **{len(report['public_leaks'])}**",
        f"- Interface conditions: **{report['summary']['interface_conditions']} (U0/U1)**",
        f"- Participant-study task subset: **{report['summary']['user_study_tasks']}**",
        "",
        "## Interpretation",
        "",
        "PASS means the specification, deterministic reset, hidden-oracle behavior, split, and run pairing are valid. "
        "It does not mean the rendered mini-site has passed keyboard or NVDA testing. Those checks are deliberately "
        "marked pending until Tahap 5/12 so accessibility claims are not fabricated.",
        "",
        "## Global gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, value in report["global_checks"].items():
        lines.append(f"| {name.replace('_', ' ')} | {'PASS' if value else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## 36 task-condition cases",
            "",
            "| Case | Domain | Reset | Oracle correct | 3 near misses | Boundary | Status | Browser/NVDA |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for case in report["cases"]:
        c = case["checks"]
        lines.append(
            f"| {case['case_id']} | {case['domain']} | "
            f"{'PASS' if c['reset_idempotent'] else 'FAIL'} | "
            f"{'PASS' if c['success_state_passes'] else 'FAIL'} | "
            f"{'PASS' if c['all_near_misses_fail'] else 'FAIL'} | "
            f"{'PASS' if c['safe_boundary_declared'] else 'FAIL'} | {case['status']} | Pending Tahap 5/12 |"
        )
    lines.extend(
        [
            "",
            "## Remaining gates",
            "",
            "1. Supervisor approval of B0/B1/P and C0/C1/C2 protocol.",
            "2. Stage 4 environment/repository freeze.",
            "3. Stage 5 rendered mini-sites, double-reset integration, keyboard walkthrough, and automated accessibility scan.",
            "4. Stage 12 runtime task-map fidelity, keyboard path, and NVDA focus-handoff validation.",
            "5. Ethics approval and the bounded 6–8 participant study comparing U0 versus U1.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_stage3.py")], check=True)
    unit_result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    cases = [validate_case(task, condition_id) for task in FINAL_TASKS for condition_id in CONDITIONS]
    final_runs = build_final_runs()
    pilot_runs = build_pilot_runs()
    leaks = public_leaks()
    reset_leaks = reset_scoring_leaks()
    manifest_checks = validate_manifest(final_runs, pilot_runs)
    collaboration_checks = validate_collaboration_contracts()
    domain_counts = Counter(task["domain"] for task in FINAL_TASKS)
    global_checks = {
        "twelve_final_tasks": len(FINAL_TASKS) == 12,
        "four_domains_three_tasks_each": domain_counts == Counter({"travel": 3, "marketplace": 3, "appointment": 3, "account": 3}),
        "three_conditions": set(CONDITIONS) == {"C0", "C1", "C2"},
        "thirty_six_cases": len(cases) == 36,
        "all_case_checks_pass": all(case["status"] == "PASS" for case in cases),
        "public_oracle_leakage_zero": not leaks,
        "reset_material_scoring_leakage_zero": not reset_leaks,
        "unit_test_suite_pass": unit_result.returncode == 0,
        **manifest_checks,
        **collaboration_checks,
    }
    report = {
        "version": STAGE3_VERSION,
        "validation_date": date.today().isoformat(),
        "overall_status": "PASS_DESIGN" if all(global_checks.values()) else "FAIL",
        "summary": {
            "tasks": len(FINAL_TASKS),
            "conditions": len(CONDITIONS),
            "cases": len(cases),
            "cases_passed": sum(case["status"] == "PASS" for case in cases),
            "near_miss_rejections": sum(
                len(FINAL_TASKS[0]["near_misses"]) if case["checks"]["all_near_misses_fail"] else 0
                for case in cases
            ),
            "final_runs": len(final_runs),
            "pilot_runs": len(pilot_runs),
            "interface_conditions": len(INTERFACE_CONDITIONS),
            "user_study_tasks": len(USER_STUDY_TASK_IDS),
        },
        "global_checks": global_checks,
        "public_leaks": leaks,
        "reset_material_scoring_leaks": reset_leaks,
        "unit_test_summary": "\n".join((unit_result.stdout + unit_result.stderr).strip().splitlines()[-4:]),
        "cases": cases,
        "browser_dependent_checks": {
            "rendered_keyboard_completion": "PENDING_STAGE_5",
            "automated_accessibility_scan": "PENDING_STAGE_5",
            "nvda_functional_validation": "PENDING_STAGE_12",
            "task_map_runtime_fidelity": "PENDING_STAGE_12",
            "focus_synchronized_handoff": "PENDING_STAGE_11_12",
            "blind_participant_study": "PENDING_STAGE_16",
        },
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "benchmark_validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (REPORT_DIR / "benchmark_validation_report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"overall_status": report["overall_status"], **report["summary"]}))
    if report["overall_status"] != "PASS_DESIGN":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
