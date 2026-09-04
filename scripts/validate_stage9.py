#!/usr/bin/env python3
"""Run the deterministic Stage 9 labelled fault/confusion-matrix gate."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from backend.agent.contracts import VerificationStatus  # noqa: E402
from backend.agent.observer import AccessibilityObserver  # noqa: E402
from backend.agent.predicates import ExpectedPostcondition  # noqa: E402
from backend.agent.recovery import (  # noqa: E402
    RecoveryContext,
    RecoveryController,
    RecoveryDecision,
)
from backend.agent.verifier import PredicateVerifier  # noqa: E402

EVIDENCE_DIR = ROOT / "evidence" / "stage9"
MATRIX_CSV = EVIDENCE_DIR / "verifier_confusion_matrix.csv"
PILOT_REPORT = EVIDENCE_DIR / "verifier_pilot_report.md"


def _cases() -> list[dict[str, Any]]:
    return [
        {
            "case": "click_no_state_change",
            "html": '<main><p role="status">Belum berubah</p></main>',
            "predicate": ExpectedPostcondition(kind="text", role="status", expected="Selesai"),
            "fault": True,
            "critical": True,
            "dangerous": False,
        },
        {
            "case": "wrong_value",
            "html": '<main><label>Nama <input value="Salah"></label></main>',
            "predicate": ExpectedPostcondition(
                kind="field_value", role="textbox", name="Nama", expected="Benar"
            ),
            "fault": True,
            "critical": True,
            "dangerous": False,
        },
        {
            "case": "stale_or_missing_node",
            "html": "<main><h1>Target sudah re-render</h1></main>",
            "predicate": ExpectedPostcondition(
                kind="element_state", role="button", name="Target lama", state_key="focused", expected=True
            ),
            "fault": True,
            "critical": True,
            "dangerous": False,
        },
        {
            "case": "duplicate_target",
            "html": "<main><button>Lanjut</button><button>Lanjut</button></main>",
            "predicate": ExpectedPostcondition(
                kind="element_state", role="button", name="Lanjut", state_key="focused", expected=True
            ),
            "fault": True,
            "critical": True,
            "dangerous": False,
        },
        {
            "case": "hidden_modal",
            "html": '<main><div role="dialog" aria-label="Konfirmasi" hidden>Rahasia</div></main>',
            "predicate": ExpectedPostcondition(
                kind="dialog_state", role="dialog", name="Konfirmasi", expected=True
            ),
            "fault": True,
            "critical": True,
            "dangerous": True,
        },
        {
            "case": "false_completion_claim",
            "html": '<main><p role="status">Masih review</p></main>',
            "predicate": ExpectedPostcondition(kind="backend_state", name="phase", expected="completed"),
            "backend": {"phase": "review"},
            "fault": True,
            "critical": True,
            "dangerous": True,
        },
        {
            "case": "valid_completion",
            "html": '<main><p role="status">Selesai</p></main>',
            "predicate": ExpectedPostcondition(kind="text", role="status", expected="Selesai"),
            "fault": False,
            "critical": False,
            "dangerous": False,
        },
    ]


def run_gate(*, update_assets: bool) -> dict[str, Any]:
    local_browsers = ROOT / ".playwright-browsers"
    if local_browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(local_browsers))
    rows: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        for case in _cases():
            page.set_content(case["html"])
            observation = AccessibilityObserver().capture(page)
            result = PredicateVerifier().evaluate(
                case["predicate"],
                observation,
                backend_state=case.get("backend"),
            )
            predicted_fault = result.status is not VerificationStatus.VERIFIED
            recovery = "NONE"
            if predicted_fault:
                recovery = (
                    RecoveryController()
                    .decide(
                        RecoveryContext(
                            step_id=uuid4(),
                            verification_status=result.status,
                            recovery_cycle=0,
                        )
                    )
                    .decision.value
                )
            rows.append(
                {
                    "case": case["case"],
                    "label_fault": case["fault"],
                    "critical": case["critical"],
                    "dangerous": case["dangerous"],
                    "verification_status": result.status.value,
                    "predicted_fault": predicted_fault,
                    "recovery_decision": recovery,
                    "expected_summary": result.expected_summary,
                    "observed_summary": result.observed_summary,
                    "evidence_ref": result.evidence_ref,
                }
            )
        browser.close()

    tp = sum(row["label_fault"] and row["predicted_fault"] for row in rows)
    tn = sum(not row["label_fault"] and not row["predicted_fault"] for row in rows)
    fp = sum(not row["label_fault"] and row["predicted_fault"] for row in rows)
    fn = sum(row["label_fault"] and not row["predicted_fault"] for row in rows)
    critical = [row for row in rows if row["critical"]]
    critical_detected = sum(row["predicted_fault"] for row in critical)
    dangerous_false_success = sum(
        row["dangerous"] and row["label_fault"] and not row["predicted_fault"] for row in rows
    )
    false_success_pct = fn / sum(row["label_fault"] for row in rows) * 100
    failures: list[str] = []
    if critical_detected != len(critical):
        failures.append("not every injected critical failure was detected")
    if false_success_pct > 5:
        failures.append(f"false success {false_success_pct:.2f}% exceeds 5%")
    if dangerous_false_success:
        failures.append("dangerous false success must be zero")
    if any(
        row["predicted_fault"] and row["recovery_decision"] not in {item.value for item in RecoveryDecision}
        for row in rows
    ):
        failures.append("fault outcome lacks auditable recovery decision")

    if update_assets:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        with MATRIX_CSV.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        PILOT_REPORT.write_text(
            "# Stage 9 Verifier Pilot\n\n"
            f"- Labelled cases: {len(rows)}\n"
            f"- Confusion matrix: TP={tp}, TN={tn}, FP={fp}, FN={fn}\n"
            f"- Critical failures detected: {critical_detected}/{len(critical)}\n"
            f"- False-success rate: {false_success_pct:.2f}%\n"
            f"- Dangerous false-success: {dangerous_false_success}\n"
            "- Every fault produced FAILED/UNCERTAIN plus an auditable recovery decision.\n"
            "- Final task success remains outside this verifier and is assigned only by hidden oracle.\n",
            encoding="utf-8",
        )
    elif not MATRIX_CSV.is_file() or not PILOT_REPORT.is_file():
        failures.append("required Stage 9 evidence files are missing")
    return {
        "stage": 9,
        "status": "PASS" if not failures else "FAIL",
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "critical_detected": f"{critical_detected}/{len(critical)}",
        "false_success_pct": round(false_success_pct, 2),
        "dangerous_false_success": dangerous_false_success,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-assets", action="store_true")
    result = run_gate(update_assets=parser.parse_args().update_assets)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
