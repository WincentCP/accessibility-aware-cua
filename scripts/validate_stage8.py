#!/usr/bin/env python3
"""Measure deterministic primitive reliability on every controlled benchmark case."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from backend.agent.executor import (  # noqa: E402
    DeterministicExecutor,
    PrimitiveAction,
    PrimitiveActionRequest,
)
from backend.agent.observer import AccessibilityObserver  # noqa: E402
from backend.agent.resolver import SemanticTargetResolver  # noqa: E402
from scripts.validate_stage7 import BASE_URL, TARGETS_PATH, test_server  # noqa: E402

REPORT = ROOT / "evidence" / "stage8" / "primitive_action_reliability.csv"


def run_gate(*, update_assets: bool) -> dict[str, object]:
    cases = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))["cases"]
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    outcomes: dict[tuple[str, str], list[tuple[bool, str]]] = {}
    local_browsers = ROOT / ".playwright-browsers"
    if local_browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(local_browsers))

    with test_server(), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        for repeat in (1, 2):
            for case in cases:
                reset = context.request.post(
                    f"{BASE_URL}/api/benchmark/reset",
                    data={key: case[key] for key in ("task_id", "condition_id", "seed")},
                )
                page.goto(f"{BASE_URL}{reset.json()['start_url']}", wait_until="networkidle")
                button = next(target for target in case["targets"] if target["role"] == "button")
                for primitive in (
                    PrimitiveAction.FOCUS,
                    PrimitiveAction.SCROLL,
                    PrimitiveAction.WAIT,
                    PrimitiveAction.ACTIVATE,
                ):
                    observer = AccessibilityObserver()
                    observation = observer.capture(page)
                    executor = DeterministicExecutor(SemanticTargetResolver(observer.registry))
                    target_ref = None
                    if primitive is not PrimitiveAction.WAIT:
                        target_ref = next(
                            node.node_id
                            for node in observation.nodes
                            if node.role == "button" and node.name == button["name"]
                        )
                    request = PrimitiveActionRequest(
                        primitive=primitive,
                        observation_version=observation.version,
                        target_ref=target_ref,
                        value="0" if primitive is PrimitiveAction.WAIT else None,
                    )
                    result = executor.execute_primitive(page, request)
                    key = (case["case_id"], primitive.value)
                    outcome = (result.success, result.error_code.value)
                    outcomes.setdefault(key, []).append(outcome)
                    rows.append(
                        {
                            "case_id": case["case_id"],
                            "repeat": repeat,
                            "primitive": primitive.value,
                            "success": result.success,
                            "error_code": result.error_code.value,
                            "duration_ms": result.duration_ms,
                            "observation_version": result.observation_version,
                            "target_role": result.target_role or "",
                            "target_name": result.target_name or "",
                            "locator_summary": result.locator_summary or "",
                        }
                    )
        browser.close()

    successes = sum(bool(row["success"]) for row in rows)
    reliability = successes / len(rows) if rows else 0.0
    inconsistent = [key for key, values in outcomes.items() if len(set(values)) != 1]
    if len(cases) != 36:
        failures.append(f"expected 36 cases, got {len(cases)}")
    if reliability < 0.95:
        failures.append(f"primitive reliability {reliability:.2%} is below 95%")
    if inconsistent:
        failures.append(f"non-deterministic repeated outcomes: {inconsistent}")
    if update_assets:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        with REPORT.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    elif not REPORT.is_file():
        failures.append("required primitive reliability report is missing")
    return {
        "stage": 8,
        "status": "PASS" if not failures else "FAIL",
        "cases": len(cases),
        "attempts": len(rows),
        "successes": successes,
        "reliability_pct": round(reliability * 100, 2),
        "repeated_outcomes_consistent": not inconsistent,
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
