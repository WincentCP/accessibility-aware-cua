#!/usr/bin/env python3
"""Run the reproducible Stage 7 observer gate across all 36 benchmark cases."""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from packages.agent.observer import AccessibilityObserver  # noqa: E402
from packages.agent.semantic_snapshot import (  # noqa: E402
    ACTIONABLE_ROLES,
    CONTEXT_CHAR_BUDGET,
    ObserverErrorCode,
    ResolutionStatus,
    TargetQuery,
    render_compact,
    within_context_budget,
)

BASE_URL = "http://127.0.0.1:8015"
TARGETS_PATH = ROOT / "benchmark" / "public" / "observer_targets.json"
GOLDEN_DIR = ROOT / "benchmark" / "golden" / "stage7"
EVIDENCE_DIR = ROOT / "evidence" / "stage7"
COVERAGE_REPORT = EVIDENCE_DIR / "observer_coverage_report.csv"
PRUNING_REPORT = EVIDENCE_DIR / "tree_pruning_efficiency_report.md"


def _ready() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=0.5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


@contextmanager
def test_server() -> Iterator[None]:
    environment = os.environ.copy()
    environment.update(
        {
            "CUA_ENV": "test",
            "CUA_APP_SECRET": "stage7-gate-secret-not-for-production",
            "CUA_REQUIRE_POSTGRES": "false",
        }
    )
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "run_test_server.py")],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not _ready():
            if process.poll() is not None:
                detail = process.stderr.read() if process.stderr else ""
                raise RuntimeError(f"test server stopped early: {detail[-1_000:]}")
            time.sleep(0.1)
        if not _ready():
            raise RuntimeError("test server did not become ready")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _normalized_snapshot(snapshot: str) -> str:
    return snapshot.rstrip() + "\n"


def _write_reports(rows: list[dict[str, Any]]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    output = StringIO()
    fieldnames = [
        "case_id",
        "targets_expected",
        "targets_found",
        "coverage_pct",
        "raw_aria_chars",
        "compact_chars",
        "reduction_pct",
        "estimated_tokens",
        "capture_latency_ms",
        "source",
        "context_budget_pass",
        "golden_match",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    COVERAGE_REPORT.write_text(output.getvalue(), encoding="utf-8")

    reductions = [float(row["reduction_pct"]) for row in rows]
    latencies = sorted(int(row["capture_latency_ms"]) for row in rows)
    p95_index = max(0, min(len(latencies) - 1, round(0.95 * len(latencies)) - 1))
    report = f"""# Stage 7 Tree-Pruning Efficiency

Generated from the pinned Playwright Chromium observer gate over all 36 public cases.

- Cases: {len(rows)}
- Mean raw ARIA size: {statistics.mean(int(row['raw_aria_chars']) for row in rows):.1f} characters
- Mean compact size: {statistics.mean(int(row['compact_chars']) for row in rows):.1f} characters
- Mean reduction: {statistics.mean(reductions):.2f}%
- Maximum compact size: {max(int(row['compact_chars']) for row in rows)} characters
- Context budget: {CONTEXT_CHAR_BUDGET} characters
- Cases within budget: {sum(row['context_budget_pass'] == 'PASS' for row in rows)}/{len(rows)}
- Mean capture latency: {statistics.mean(int(row['capture_latency_ms']) for row in rows):.1f} ms
- P95 capture latency: {latencies[p95_index]} ms
- Coordinates, task-specific CSS selectors, test IDs, and private oracle fields in planner snapshot: none

The compact snapshot preserves landmarks, headings, form controls, status/error semantics,
dialog/note content, values, states, focus, and observation-scoped references. App chrome,
extension namespace content, generic wrappers, and duplicate non-actionable text are pruned.
"""
    PRUNING_REPORT.write_text(report, encoding="utf-8")


def run_gate(*, update_assets: bool) -> dict[str, Any]:
    inventory = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    cases = inventory["cases"]
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    expected_total = 0
    found_total = 0
    stale_checks = 0
    previous_ref: str | None = None

    local_browsers = ROOT / ".playwright-browsers"
    if local_browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(local_browsers))

    if update_assets:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    with test_server(), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        observer = AccessibilityObserver()
        for case in cases:
            reset = context.request.post(
                f"{BASE_URL}/api/benchmark/reset",
                data={
                    "task_id": case["task_id"],
                    "condition_id": case["condition_id"],
                    "seed": case["seed"],
                },
            )
            if not reset.ok:
                failures.append(f"{case['case_id']}: reset HTTP {reset.status}")
                continue
            start_url = reset.json()["start_url"]
            page.goto(f"{BASE_URL}{start_url}", wait_until="networkidle")
            raw_aria = _normalized_snapshot(page.locator("body").aria_snapshot())
            observation = observer.capture(page)
            compact = render_compact(observation)
            if previous_ref is not None:
                stale_checks += 1
                if (
                    observer.registry.resolve_ref(previous_ref).error_code
                    is not ObserverErrorCode.STALE_OBSERVATION
                ):
                    failures.append(f"{case['case_id']}: old semantic ref remained valid")
            previous_ref = observation.nodes[0].node_id if observation.nodes else None

            found = 0
            expected = len(case["targets"])
            expected_total += expected
            for target in case["targets"]:
                query = TargetQuery(
                    **target,
                    observation_version=observation.version,
                )
                resolution = observer.registry.query(query)
                if resolution.status is not ResolutionStatus.FOUND:
                    failures.append(
                        f"{case['case_id']}: {target['role']} {target['name']!r} -> "
                        f"{resolution.error_code.value}"
                    )
                    continue
                found += 1
                if target["role"] in ACTIONABLE_ROLES:
                    try:
                        observer.locator_for(page, query)
                    except Exception as exc:
                        failures.append(
                            f"{case['case_id']}: semantic action locator failed: "
                            f"{type(exc).__name__}"
                        )
            found_total += found

            forbidden = ["data-testid", "css_selector", "expected_record_id", "x=", "y="]
            for token in forbidden:
                if token in compact:
                    failures.append(f"{case['case_id']}: forbidden planner token {token!r}")

            golden_path = GOLDEN_DIR / f"{case['case_id']}.aria.yml"
            if update_assets:
                golden_path.write_text(raw_aria, encoding="utf-8")
                golden_match = True
            else:
                golden_match = golden_path.is_file() and golden_path.read_text(
                    encoding="utf-8"
                ) == raw_aria
                if not golden_match:
                    failures.append(f"{case['case_id']}: golden ARIA snapshot mismatch")

            reduction = (
                (observation.raw_char_count - observation.compact_char_count)
                / observation.raw_char_count
                * 100
                if observation.raw_char_count
                else 0.0
            )
            budget_pass = within_context_budget(observation)
            if not budget_pass:
                failures.append(f"{case['case_id']}: compact snapshot exceeds context budget")
            rows.append(
                {
                    "case_id": case["case_id"],
                    "targets_expected": expected,
                    "targets_found": found,
                    "coverage_pct": f"{found / expected * 100:.2f}",
                    "raw_aria_chars": observation.raw_char_count,
                    "compact_chars": observation.compact_char_count,
                    "reduction_pct": f"{reduction:.2f}",
                    "estimated_tokens": observation.estimated_tokens,
                    "capture_latency_ms": observation.capture_latency_ms,
                    "source": observation.source,
                    "context_budget_pass": "PASS" if budget_pass else "FAIL",
                    "golden_match": "PASS" if golden_match else "FAIL",
                }
            )
        browser.close()

    coverage = found_total / expected_total if expected_total else 0.0
    if len(rows) != 36:
        failures.append(f"expected 36 observed cases, got {len(rows)}")
    if coverage < 0.95:
        failures.append(f"semantic target coverage {coverage:.2%} is below 95%")
    if stale_checks != 35:
        failures.append(f"expected 35 stale-reference checks, got {stale_checks}")
    if update_assets:
        _write_reports(rows)
    elif not COVERAGE_REPORT.is_file() or not PRUNING_REPORT.is_file():
        failures.append("required Stage 7 measurement reports are missing")

    return {
        "stage": 7,
        "status": "PASS" if not failures else "FAIL",
        "cases": len(rows),
        "semantic_targets": {"found": found_total, "expected": expected_total},
        "coverage_pct": round(coverage * 100, 2),
        "stale_reference_checks": stale_checks,
        "context_budget_chars": CONTEXT_CHAR_BUDGET,
        "max_compact_chars": max((int(row["compact_chars"]) for row in rows), default=0),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update-assets",
        action="store_true",
        help="Review and replace golden ARIA snapshots and measurement reports.",
    )
    args = parser.parse_args()
    result = run_gate(update_assets=args.update_assets)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
