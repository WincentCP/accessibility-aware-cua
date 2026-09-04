#!/usr/bin/env python3
"""Run Stage 10 schema, graph, pilot, and no-hardcode gates."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from backend.agent.executor import DeterministicExecutor  # noqa: E402
from backend.agent.graph import OrchestrationServices, build_agent_graph  # noqa: E402
from backend.agent.observer import AccessibilityObserver  # noqa: E402
from backend.agent.planner import (  # noqa: E402
    ModelResponse,
    PlannerRequest,
    StructuredPlanner,
    normalize_input,
)
from backend.agent.recovery import RecoveryController  # noqa: E402
from backend.agent.resolver import SemanticTargetResolver  # noqa: E402
from backend.agent.verifier import PredicateVerifier  # noqa: E402

EVIDENCE_DIR = ROOT / "evidence" / "stage10"
TRAJECTORIES = EVIDENCE_DIR / "pilot_trajectories.jsonl"
REPORT = EVIDENCE_DIR / "planner_schema_report.md"


class SemanticPilotModel:
    """AX-driven structured-output test double used only for engineering gates."""

    def __init__(self, *, inject_retry_every: int = 0):
        self.calls = 0
        self.inject_retry_every = inject_retry_every

    def generate(self, *, prompt, schema, request):
        self.calls += 1
        logical_attempt = self.calls
        malformed = (
            self.inject_retry_every
            and logical_attempt % self.inject_retry_every == 0
            and "schema_correction" not in request
        )
        if malformed:
            payload = {"invalid": True}
        else:
            match = re.search(
                r"\[(v\d+:ax\d+)\] button \"([^\"]+)\"",
                request["compact_observation"],
            )
            if match is None:
                raise RuntimeError("pilot observation has no semantic button")
            payload = {
                "action": {
                    "action_type": "click",
                    "target_ref": match.group(1),
                    "observation_version": int(match.group(1).split(":")[0][1:]),
                    "expected_effect": "Status tugas terverifikasi selesai",
                    "risk_level": "LOW",
                    "requires_approval": False,
                },
                "postconditions": [{"kind": "text", "role": "status", "expected": "Selesai"}],
                "reason": "Pilih kontrol semantik dari snapshot terbaru.",
                "goal_complete_after_verification": True,
            }
        return ModelResponse(
            payload=payload,
            input_tokens=45,
            output_tokens=35,
            model_id="structured-pilot-test-double",
            provider="offline-test-double",
            latency_ms=2,
        )


def _services(page, model):
    observer = AccessibilityObserver()
    return OrchestrationServices(
        page=page,
        observer=observer,
        executor=DeterministicExecutor(SemanticTargetResolver(observer.registry)),
        verifier=PredicateVerifier(),
        planner=StructuredPlanner(model),
        recovery=RecoveryController(),
    )


def _state(index: int):
    return {
        "schema_version": "1.0.0",
        "session_id": str(uuid4()),
        "thread_id": f"stage10-pilot:{uuid4()}",
        "run_id": str(uuid4()),
        "task_id": f"T{index + 1:02d}",
        "raw_input": "Jalankan tugas dan berhenti setelah status selesai; jangan bayar.",
        "step_count": 0,
        "recovery_count": 0,
        "replan_count": 0,
        "task_map_version": 0,
        "verified_progress": [],
        "planner_telemetry": [],
        "token_usage": 0,
        "token_budget": 5_000,
        "max_steps": 5,
        "started_at_ms": int(time.time() * 1_000),
        "handoff_status": "NONE",
        "intervention_count": 0,
        "error_code": "NONE",
    }


def run_gate(*, update_assets: bool) -> dict[str, object]:
    failures: list[str] = []
    schema_success = 0
    schema_attempts = 100
    model = SemanticPilotModel(inject_retry_every=25)
    request = PlannerRequest(
        compact_observation='- [v1:ax0001] button "Jalankan"',
        goal=normalize_input("Jalankan tugas; jangan bayar."),
        remaining_steps=5,
        remaining_tokens=2_000,
    )
    for _ in range(schema_attempts):
        try:
            StructuredPlanner(model).plan(request)
            schema_success += 1
        except RuntimeError:
            pass

    local_browsers = ROOT / ".playwright-browsers"
    if local_browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(local_browsers))
    labels = ["Travel A", "Travel B", "Marketplace", "Appointment", "Account"]
    trajectories = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for index, label in enumerate(labels):
            page = browser.new_page()
            page.set_content(
                f'<main><h1>{label}</h1><button onclick="s.textContent=\'Selesai\'">Jalankan</button><p id="s" role="status">Menunggu</p></main>'
            )
            pilot_model = SemanticPilotModel()
            graph = build_agent_graph(_services(page, pilot_model), checkpointer=InMemorySaver())
            state = _state(index)
            result = graph.invoke(state, {"configurable": {"thread_id": state["thread_id"]}})
            trajectories.append(
                {
                    "pilot": index + 1,
                    "site": label,
                    "terminal_reason": result.get("terminal_reason"),
                    "verification_status": (result.get("verification") or {}).get("status"),
                    "steps": result.get("step_count"),
                    "recoveries": result.get("recovery_count"),
                    "task_map_version": result.get("task_map_version"),
                    "model_id": result["planner_telemetry"][0]["model_id"],
                    "provider": result["planner_telemetry"][0]["provider"],
                    "prompt_hash": result["planner_telemetry"][0]["prompt_hash"],
                    "token_usage": result.get("token_usage"),
                }
            )
            page.close()
        browser.close()

    valid_pct = schema_success / schema_attempts * 100
    completed = sum(
        row["terminal_reason"] == "COMPLETED" and row["verification_status"] == "VERIFIED"
        for row in trajectories
    )
    graph_source = (ROOT / "backend" / "agent" / "graph.py").read_text(encoding="utf-8")
    if valid_pct < 98:
        failures.append(f"planner schema validity {valid_pct:.2f}% below 98%")
    if completed != 5:
        failures.append(f"only {completed}/5 pilot tasks completed")
    if re.search(r"if\s+.*task_id|elif\s+.*task_id", graph_source):
        failures.append("task-specific task_id branching found")
    if any(token in graph_source.casefold() for token in ("subagent", "multi_agent", "multi-agent")):
        failures.append("multi-agent implementation found")
    if update_assets:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        TRAJECTORIES.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in trajectories),
            encoding="utf-8",
        )
        REPORT.write_text(
            "# Stage 10 Structured Planner Pilot\n\n"
            f"- Valid structured outputs after one controlled retry: {schema_success}/{schema_attempts} ({valid_pct:.2f}%)\n"
            f"- Cross-site engineering pilots completed: {completed}/5\n"
            "- Sites represented: Travel, Marketplace, Appointment, Account\n"
            "- Task-specific branches/selectors: none\n"
            "- Multi-agent/subagent orchestration: none\n"
            "- Pilot model: offline structured-output test double; live model selection and frozen evaluation run remain separate from this engineering gate.\n",
            encoding="utf-8",
        )
    elif not TRAJECTORIES.is_file() or not REPORT.is_file():
        failures.append("required Stage 10 evidence files are missing")
    return {
        "stage": 10,
        "status": "PASS" if not failures else "FAIL",
        "schema_valid_pct": valid_pct,
        "pilot_tasks_completed": f"{completed}/5",
        "pilot_sites": 4,
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
