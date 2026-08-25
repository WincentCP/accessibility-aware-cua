#!/usr/bin/env python3
"""Build the explicit public 36-case semantic-target inventory."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmark" / "public" / "observer_targets.json"

PRIMARY_BUTTON = {
    "T01": "Simpan pilihan dan buka review",
    "T02": "Terapkan filter dan buka review",
    "T03": "Simpan data dummy dan lanjut ke review",
    "T04": "Simpan ke perbandingan",
    "T05": "Tambahkan ke cart sintetis",
    "T06": "Simpan sebagai draft",
    "T07": "Simpan slot untuk review",
    "T08": "Simpan form dan minta approval",
    "T09": "Simpan draft di checkpoint approval",
    "T10": "Simpan preferensi notifikasi",
    "T11": "Terapkan dan render ulang",
    "T12": "Simpan draft profil",
}


def main() -> int:
    task_payload = json.loads(
        (ROOT / "benchmark" / "public" / "task_specs.json").read_text(encoding="utf-8")
    )
    case_payload = json.loads(
        (ROOT / "benchmark" / "public" / "case_matrix.json").read_text(encoding="utf-8")
    )
    task_by_id = {task["id"]: task for task in task_payload["tasks"]}
    cases = []
    for index, case in enumerate(case_payload["cases"]):
        task = task_by_id[case["task_id"]]
        cases.append(
            {
                "case_id": case["case_id"],
                "task_id": case["task_id"],
                "condition_id": case["condition_id"],
                "seed": 970_000 + index,
                "targets": [
                    {"role": "heading", "name": task["name"], "states": {"level": 1}},
                    {
                        "role": "status",
                        "name": "Fixture siap. Belum ada aksi yang dicatat.",
                        "states": {},
                    },
                    {
                        "role": "button",
                        "name": PRIMARY_BUTTON[case["task_id"]],
                        "states": {},
                    },
                ],
            }
        )
    payload = {
        "version": "0.7.0-observer-targets",
        "purpose": "Oracle-independent semantic targets for Stage 7 observer coverage.",
        "forbidden_fields": ["oracle", "expected_record_id", "data-testid", "css_selector", "x", "y"],
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases to {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
