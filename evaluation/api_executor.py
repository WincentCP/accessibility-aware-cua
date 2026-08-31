"""Sequential live executor using the local API and isolated browser bridge."""

from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx

from evaluation.config import TreatmentConfig
from evaluation.contracts import ExecutionOutcome, ManifestRun
from evaluation.visual_baseline import (
    VISUAL_PROMPT_HASH,
    GeminiVisualClient,
    VisualBaselineRunner,
    VisualBridge,
)
from packages.agent.planner import PROMPT_PATH, PROMPT_VERSION
from packages.agent.remote_page import RemotePage

TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


class ApiRunExecutor:
    def __init__(
        self,
        *,
        api_url: str,
        bridge_url: str,
        app_secret: str,
        gemini_api_key: str,
        planner_model: str,
        planner_fallback_model: str | None,
        gemini_max_retries: int,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.bridge_url = bridge_url.rstrip("/")
        self.app_secret = app_secret
        self.gemini_api_key = gemini_api_key
        self.planner_model = planner_model
        self.planner_fallback_model = planner_fallback_model
        self.gemini_max_retries = gemini_max_retries
        self.timeout_seconds = timeout_seconds

    def configuration_fingerprint(self, config: TreatmentConfig) -> dict[str, Any]:
        prompt_hash = (
            VISUAL_PROMPT_HASH
            if config.configuration.value == "B0"
            else hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()
        )
        return {
            "planner_model": self.planner_model,
            "planner_fallback_model": self.planner_fallback_model,
            "gemini_max_retries": self.gemini_max_retries,
            "prompt_hash": prompt_hash,
        }

    def execute(self, run: ManifestRun, config: TreatmentConfig) -> ExecutionOutcome:
        config.require_ready()
        started = time.perf_counter()
        with httpx.Client(base_url=self.api_url, timeout=10.0, trust_env=False) as client:
            reset_response = client.post(
                "/api/benchmark/reset",
                json={
                    "task_id": run.task_id,
                    "condition_id": run.condition_id,
                    "seed": run.seed,
                },
            )
            reset_response.raise_for_status()
            reset = reset_response.json()
            page = RemotePage(self.bridge_url, self.app_secret)
            try:
                browser_health = page.health()
                page.goto(f"{self.api_url}{reset['start_url']}", wait_until="domcontentloaded", timeout=10_000)
            finally:
                page.close()
            if run.configuration.value == "B0":
                view_response = client.get(f"/api/benchmark/sessions/{reset['session_id']}")
                view_response.raise_for_status()
                task = view_response.json()["task"]
                bridge = VisualBridge(self.bridge_url, self.app_secret)
                model = GeminiVisualClient(
                    self.gemini_api_key,
                    model=self.planner_model,
                    fallback_model=self.planner_fallback_model,
                    max_retries=self.gemini_max_retries,
                )
                try:
                    outcome = VisualBaselineRunner(bridge=bridge, model=model).run(
                        goal=task["goal"],
                        forbidden_actions=task["forbidden_actions"],
                        completion_boundary=task["completion_boundary"],
                        max_steps=int(task["max_steps"]),
                        token_budget=config.token_budget,
                    )
                finally:
                    bridge.close()
                    model.close()
                oracle_response = client.get(
                    f"/internal/evaluation/sessions/{reset['session_id']}/oracle",
                    headers={"Authorization": f"Bearer {self.app_secret}"},
                )
                oracle_response.raise_for_status()
                return outcome.model_copy(
                    update={
                        "oracle_result": oracle_response.json(),
                        "runtime_metadata": {
                            **outcome.runtime_metadata,
                            "browser_version": browser_health.get("browser_version"),
                        },
                    }
                )
            response = client.post(
                "/api/agent/runs",
                json={
                    "benchmark_session_id": reset["session_id"],
                    "configuration": run.configuration.value,
                },
            )
            response.raise_for_status()
            snapshot: dict[str, Any] = response.json()
            deadline = time.monotonic() + self.timeout_seconds
            automatic_approvals = 0
            while snapshot["status"] not in TERMINAL_STATUSES:
                if snapshot["status"] == "WAITING_USER":
                    pending_kind = (snapshot.get("pending_interaction") or {}).get("kind")
                    if pending_kind != "APPROVAL":
                        break
                    approval = client.post(
                        f"/api/agent/runs/{snapshot['run_id']}/commands",
                        json={"command": "APPROVE"},
                    )
                    approval.raise_for_status()
                    snapshot = approval.json()
                    automatic_approvals += 1
                    continue
                if time.monotonic() >= deadline:
                    return ExecutionOutcome(
                        terminal_reason="TIMEOUT",
                        error_code="INFRASTRUCTURE_TIMEOUT",
                        duration_ms=round((time.perf_counter() - started) * 1_000),
                        infrastructure_error="Live run melewati batas waktu evaluator.",
                    )
                time.sleep(0.2)
                poll = client.get(f"/api/agent/runs/{snapshot['run_id']}")
                poll.raise_for_status()
                snapshot = poll.json()
            oracle_response = client.get(
                f"/internal/evaluation/sessions/{reset['session_id']}/oracle",
                headers={"Authorization": f"Bearer {self.app_secret}"},
            )
            oracle_response.raise_for_status()
        metrics = snapshot.get("metrics") or {}
        started_at_ms = int(metrics.get("started_at_ms", 0))
        duration_ms = (
            max(0, int(time.time() * 1_000) - started_at_ms)
            if started_at_ms
            else round((time.perf_counter() - started) * 1_000)
        )
        return ExecutionOutcome(
            agent_claimed_success=snapshot["status"] == "COMPLETED",
            terminal_reason=snapshot["status"],
            error_code=(snapshot.get("error") or "NONE")[:80],
            oracle_result=oracle_response.json(),
            step_count=int(metrics.get("step_count", 0)),
            recovery_count=int(metrics.get("recovery_count", 0)),
            intervention_count=int(metrics.get("intervention_count", 0)),
            duration_ms=duration_ms,
            runtime_metadata={
                "model_id": ",".join(metrics.get("planner_models") or []) or self.planner_model,
                "prompt_version": ",".join(metrics.get("prompt_versions") or [])
                or PROMPT_VERSION,
                "prompt_hash": ",".join(metrics.get("prompt_hashes") or [])
                or hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest(),
                "browser_version": browser_health.get("browser_version"),
                "automatic_approvals": automatic_approvals,
            },
        )
