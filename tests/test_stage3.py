from __future__ import annotations

import json
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from a11y_benchmark.catalog import (  # noqa: E402
    CONDITIONS,
    FINAL_TASKS,
    HANDOFF_ORACLES,
    INTERFACE_CONDITIONS,
    PILOT_TASKS,
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

FORBIDDEN_PUBLIC_KEYS = {
    "initial_state",
    "success_patch",
    "predicates",
    "invariants",
    "near_misses",
    "expected_final_state",
    "target_id",
    "oracle",
    "handoff_oracle",
    "handoff_trigger",
    "focus_target",
    "context_record_id",
}


def all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from all_keys(nested)


class Stage3CatalogTests(unittest.TestCase):
    def test_final_catalog_shape(self):
        self.assertEqual(len(FINAL_TASKS), 12)
        self.assertEqual([t["id"] for t in FINAL_TASKS], [f"T{i:02d}" for i in range(1, 13)])
        self.assertEqual(Counter(t["domain"] for t in FINAL_TASKS), {
            "travel": 3, "marketplace": 3, "appointment": 3, "account": 3
        })
        self.assertEqual(set(CONDITIONS), {"C0", "C1", "C2"})

    def test_each_task_has_bounded_keyboard_safe_contract(self):
        for task in FINAL_TASKS:
            with self.subTest(task=task["id"]):
                self.assertGreaterEqual(len(task["keyboard_path"]), 2)
                self.assertNotIn("mouse", " ".join(task["keyboard_path"]).lower())
                self.assertLessEqual(task["max_steps"], 30)
                self.assertGreaterEqual(len(task["allowed_actions"]), 1)
                self.assertGreaterEqual(len(task["forbidden_actions"]), 1)
                self.assertEqual(task["data_policy"], "synthetic_only")
                self.assertEqual(set(task["condition_challenges"]), {"C0", "C1", "C2"})
                self.assertEqual(len(task["near_misses"]), 3)

    def test_no_live_url_or_real_transaction_dependency(self):
        for task in FINAL_TASKS + PILOT_TASKS:
            with self.subTest(task=task["id"]):
                self.assertTrue(task["start_route"].startswith("/"))
                self.assertNotIn("http://", task["start_route"])
                self.assertNotIn("https://", task["start_route"])
                self.assertIn("synthetic", task["data_policy"])


class Stage3ResetAndOracleTests(unittest.TestCase):
    def test_all_36_cases_reset_idempotently(self):
        seen = 0
        for task in FINAL_TASKS:
            for condition_id in CONDITIONS:
                seed = final_seed(task["id"], condition_id, 1)
                first = reset_case(task["id"], condition_id, seed)
                second = reset_case(task["id"], condition_id, seed)
                with self.subTest(task=task["id"], condition=condition_id):
                    self.assertEqual(first, second)
                    self.assertEqual(first["snapshot_hash"], second["snapshot_hash"])
                seen += 1
        self.assertEqual(seen, 36)

    def test_oracle_passes_correct_and_rejects_all_near_misses(self):
        count = 0
        for task in FINAL_TASKS:
            for condition_id in CONDITIONS:
                seed = final_seed(task["id"], condition_id, 1)
                correct = success_state(task["id"], condition_id, seed)
                with self.subTest(task=task["id"], condition=condition_id, state="correct"):
                    self.assertTrue(evaluate(task["id"], correct)["pass"])
                misses = near_miss_states(task["id"], condition_id, seed)
                self.assertGreaterEqual(len(misses), 3)
                for miss in misses:
                    with self.subTest(task=task["id"], condition=condition_id, state=miss["id"]):
                        self.assertFalse(evaluate(task["id"], miss["state"])["pass"])
                count += 1
        self.assertEqual(count, 36)

    def test_public_build_contains_no_hidden_oracle_keys(self):
        for path in sorted((ROOT / "benchmark" / "public").glob("*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            leaked = set(all_keys(value)) & FORBIDDEN_PUBLIC_KEYS
            with self.subTest(path=path.name):
                self.assertEqual(leaked, set())

    def test_reset_material_contains_no_scoring_truth(self):
        value = json.loads(
            (ROOT / "benchmark" / "reset" / "reset_material.json").read_text(encoding="utf-8")
        )
        scoring_keys = {
            "success_patch", "predicates", "invariants", "near_misses",
            "expected_final_state", "target_id", "oracle",
        }
        self.assertEqual(set(all_keys(value)) & scoring_keys, set())

    def test_seeded_visible_variants_preserve_logical_solution(self):
        for condition_id in CONDITIONS:
            for repetition in (1, 2, 3):
                scenarios = {}
                for task_id in ("T01", "T02", "T04", "T07"):
                    seed = final_seed(task_id, condition_id, repetition)
                    records = reset_case(task_id, condition_id, seed)["public_fixture"]["records"]
                    scenarios[task_id] = records

                t01_valid = [r for r in scenarios["T01"] if r["price"] <= 900000 and "09:00" <= r["depart"] <= "11:30"]
                self.assertEqual([r["id"] for r in t01_valid], ["tr01"])

                t02_valid = [r for r in scenarios["T02"] if r["stops"] == 0 and r["arrive"] <= "18:00"]
                self.assertEqual(min(t02_valid, key=lambda r: r["price"])["id"], "tr11")

                t04_valid = [r for r in scenarios["T04"] if r["price"] <= 750000 and r["rating"] >= 4.6]
                self.assertEqual([r["id"] for r in t04_valid], ["mp01"])

                t07_valid = [r for r in scenarios["T07"] if r["day"] == "Selasa" and "13:00" <= r["time"] <= "15:00" and r["advisor"] == "Rina"]
                self.assertEqual([r["id"] for r in t07_valid], ["ap01"])


class Stage3ManifestTests(unittest.TestCase):
    def test_final_manifest_is_324_paired_runs(self):
        runs = build_final_runs()
        self.assertEqual(len(runs), 324)
        groups = defaultdict(list)
        for run in runs:
            groups[run["pair_id"]].append(run)
        self.assertEqual(len(groups), 108)
        for pair_id, group in groups.items():
            with self.subTest(pair_id=pair_id):
                self.assertEqual({r["configuration"] for r in group}, {"B0", "B1", "P"})
                self.assertEqual(len({r["seed"] for r in group}), 1)
                self.assertEqual(len({r["variant_hash"] for r in group}), 1)
                repetition = group[0]["repetition"]
                ordered = [r["configuration"] for r in sorted(group, key=lambda item: item["order_position"])]
                self.assertEqual(ordered, LATIN_ORDERS[repetition - 1])

    def test_pilot_is_24_runs_and_disjoint(self):
        final_runs = build_final_runs()
        pilot_runs = build_pilot_runs()
        self.assertEqual(len(pilot_runs), 24)
        self.assertTrue(all(r["task_id"].startswith("P") for r in pilot_runs))
        self.assertTrue(all(r["task_id"].startswith("T") for r in final_runs))
        self.assertTrue({r["seed"] for r in pilot_runs}.isdisjoint({r["seed"] for r in final_runs}))


class Stage3AccessibleCollaborationTests(unittest.TestCase):
    def test_u0_u1_isolate_task_map_and_focus_handoff(self):
        self.assertEqual(set(INTERFACE_CONDITIONS), {"U0", "U1"})
        u0 = INTERFACE_CONDITIONS["U0"]
        u1 = INTERFACE_CONDITIONS["U1"]
        self.assertEqual(u0["core_agent"], u1["core_agent"])
        self.assertFalse(u0["task_map"])
        self.assertFalse(u0["focus_synchronized_handoff"])
        self.assertTrue(u1["task_map"])
        self.assertTrue(u1["verified_progress_evidence"])
        self.assertTrue(u1["focus_synchronized_handoff"])
        self.assertEqual(u0["controls"], u1["controls"])

    def test_public_tasks_have_verified_collaboration_contract(self):
        for task in FINAL_TASKS:
            contract = public_task(task)["collaboration_contract"]
            with self.subTest(task=task["id"]):
                self.assertEqual(contract["completed_claim_policy"], "VERIFIED_ONLY")
                self.assertEqual(contract["relevant_item_grounding"], "LATEST_AX_SNAPSHOT")
                self.assertTrue(contract["stale_entries_invalidated"])
                self.assertTrue(contract["resume_requires_fresh_observation"])

    def test_user_study_subset_has_private_handoff_oracles(self):
        self.assertEqual(USER_STUDY_TASK_IDS, ["T01", "T04", "T08", "T11"])
        self.assertEqual(set(HANDOFF_ORACLES), set(USER_STUDY_TASK_IDS))
        for task_id, oracle in HANDOFF_ORACLES.items():
            with self.subTest(task=task_id):
                self.assertIn("role", oracle["focus_target"])
                self.assertIn("name_pattern", oracle["focus_target"])
                self.assertLessEqual(oracle["max_navigation_keystrokes"], 12)

    def test_task_map_schema_prevents_unverified_completion_claim(self):
        schema = json.loads(
            (ROOT / "benchmark" / "schemas" / "task_map_snapshot.schema.json").read_text(encoding="utf-8")
        )
        completed = schema["properties"]["verified_completed_steps"]["items"]
        self.assertEqual(completed["properties"]["verification_status"], {"const": "VERIFIED"})
        self.assertIn("evidence_ref", completed["required"])
        next_action = schema["properties"]["next_action"]["properties"]
        self.assertEqual(next_action["status"], {"const": "PLANNED_NOT_COMPLETED"})


if __name__ == "__main__":
    unittest.main()
