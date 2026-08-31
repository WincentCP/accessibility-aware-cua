from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from a11y_benchmark.oracles.engine import success_state
from a11y_benchmark.reset.engine import reset_case
from apps.api.a11y_api.app import create_app
from apps.api.a11y_api.config import ROOT, Settings
from evaluation.config import (
    CONFIGURATIONS,
    EvaluationConfiguration,
    validate_treatment_isolation,
)
from evaluation.contracts import ExecutionOutcome, FailureClass
from evaluation.report import build_summary, write_reports
from evaluation.runner import EvaluationRunner, load_manifest, validate_pilot_gate
from evaluation.storage import JsonResultStore, MemoryResultStore
from evaluation.visual_baseline import (
    GeminiVisualClient,
    Screenshot,
    VisualBaselineRunner,
    VisualBridge,
)

PILOT_MANIFEST = ROOT / "benchmark/private/manifests/pilot_runs.json"
FINAL_MANIFEST = ROOT / "benchmark/private/manifests/final_runs.json"


class StaticExecutor:
    def __init__(self, outcome: ExecutionOutcome) -> None:
        self.outcome = outcome
        self.calls = 0

    def execute(self, run, config):
        self.calls += 1
        return self.outcome


class FlakyExecutor:
    def __init__(self, final_state: dict) -> None:
        self.final_state = final_state
        self.calls = 0

    def execute(self, run, config):
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("bridge unavailable")
        return ExecutionOutcome(
            agent_claimed_success=True,
            terminal_reason="COMPLETED",
            final_state=self.final_state,
        )


class FingerprintedExecutor(StaticExecutor):
    def __init__(self, outcome: ExecutionOutcome, fingerprint: str) -> None:
        super().__init__(outcome)
        self.fingerprint = fingerprint

    def configuration_fingerprint(self, config):
        return {"model_and_prompt": self.fingerprint}


def _one_ready_run():
    return next(
        run
        for run in load_manifest(PILOT_MANIFEST)
        if run.configuration is EvaluationConfiguration.B1
    )


def _settings() -> Settings:
    return Settings(
        environment="test",
        app_secret="test-secret",
        host="127.0.0.1",
        port=8000,
        require_postgres=False,
        database_url="postgresql://unused",
        browser_profile_dir=Path(".runtime/test"),
        browser_headless=True,
        planner_provider="deterministic",
    )


def test_locked_manifests_load_with_expected_sizes_and_fair_pairs() -> None:
    assert len(load_manifest(PILOT_MANIFEST)) == 24
    assert len(load_manifest(FINAL_MANIFEST)) == 324


def test_manifest_rejects_split_task_mismatch(tmp_path: Path) -> None:
    payload = json.loads(PILOT_MANIFEST.read_text(encoding="utf-8"))
    payload["runs"][0]["split"] = "final"
    payload["runs"][0]["repetition"] = 1
    invalid = tmp_path / "invalid-split.json"
    invalid.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Task dan split"):
        load_manifest(invalid)


def test_manifest_rejects_extra_run_in_pair(tmp_path: Path) -> None:
    payload = json.loads(PILOT_MANIFEST.read_text(encoding="utf-8"))
    duplicate = dict(payload["runs"][0])
    duplicate["run_id"] = "PILOT-P01-C0-B0-DUPLICATE"
    payload["runs"].append(duplicate)
    invalid = tmp_path / "invalid-pair.json"
    invalid.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="tepat tiga run"):
        load_manifest(invalid)


def test_treatments_are_isolated_and_visual_baseline_is_distinct() -> None:
    validate_treatment_isolation()
    assert not CONFIGURATIONS[EvaluationConfiguration.B1].bounded_recovery
    assert CONFIGURATIONS[EvaluationConfiguration.PROPOSED].bounded_recovery
    assert CONFIGURATIONS[EvaluationConfiguration.B0].observation_mode == "screenshot"
    assert CONFIGURATIONS[EvaluationConfiguration.B0].action_grounding == "coordinates"
    assert CONFIGURATIONS[EvaluationConfiguration.B0].implementation_ready


def test_hidden_oracle_overrides_false_agent_success_claim() -> None:
    run = _one_ready_run()
    executor = StaticExecutor(
        ExecutionOutcome(
            agent_claimed_success=True,
            terminal_reason="COMPLETED",
            final_state=reset_case(run.task_id, run.condition_id, run.seed)["state"],
        )
    )
    result = EvaluationRunner(executor=executor, store=MemoryResultStore()).run([run])[0]
    assert result.agent_claimed_success is True
    assert result.oracle_success is False
    assert result.failure_class is FailureClass.AGENT


def test_hidden_oracle_accepts_state_even_if_agent_did_not_claim_completion() -> None:
    run = _one_ready_run()
    executor = StaticExecutor(
        ExecutionOutcome(
            agent_claimed_success=False,
            terminal_reason="ERROR",
            final_state=success_state(run.task_id, run.condition_id, run.seed),
        )
    )
    result = EvaluationRunner(executor=executor, store=MemoryResultStore()).run([run])[0]
    assert result.oracle_success is True
    assert result.failure_class is FailureClass.NONE


def test_infrastructure_failure_retries_then_resume_skips_completed_run() -> None:
    run = _one_ready_run()
    store = MemoryResultStore()
    executor = FlakyExecutor(success_state(run.task_id, run.condition_id, run.seed))
    runner = EvaluationRunner(executor=executor, store=store, infrastructure_retries=1)
    results = runner.run([run])
    assert [item.failure_class for item in results] == [
        FailureClass.INFRASTRUCTURE,
        FailureClass.NONE,
    ]
    assert executor.calls == 2
    assert runner.run([run]) == []
    assert executor.calls == 2


def test_json_store_resumes_after_process_boundary(tmp_path: Path) -> None:
    run = _one_ready_run()
    path = tmp_path / "evaluation-results.json"
    executor = StaticExecutor(
        ExecutionOutcome(
            terminal_reason="COMPLETED",
            final_state=success_state(run.task_id, run.condition_id, run.seed),
        )
    )
    EvaluationRunner(executor=executor, store=JsonResultStore(path)).run([run])
    restarted = JsonResultStore(path)
    second_executor = StaticExecutor(
        ExecutionOutcome(
            terminal_reason="COMPLETED",
            final_state=success_state(run.task_id, run.condition_id, run.seed),
        )
    )
    assert EvaluationRunner(executor=second_executor, store=restarted).run([run]) == []
    assert second_executor.calls == 0


def test_changed_config_hash_forces_rerun_instead_of_reusing_stale_result() -> None:
    run = _one_ready_run()
    initial_executor = StaticExecutor(
        ExecutionOutcome(
            terminal_reason="COMPLETED",
            final_state=success_state(run.task_id, run.condition_id, run.seed),
        )
    )
    initial_store = MemoryResultStore()
    initial = EvaluationRunner(executor=initial_executor, store=initial_store).run([run])[0]
    stale = initial.model_copy(update={"config_hash": "0" * 64})
    executor = StaticExecutor(
        ExecutionOutcome(
            terminal_reason="COMPLETED",
            final_state=success_state(run.task_id, run.condition_id, run.seed),
        )
    )
    produced = EvaluationRunner(executor=executor, store=MemoryResultStore([stale])).run([run])
    assert len(produced) == 1
    assert produced[0].attempt == 2


def test_changed_runtime_fingerprint_forces_rerun() -> None:
    run = _one_ready_run()
    outcome = ExecutionOutcome(
        terminal_reason="COMPLETED",
        final_state=success_state(run.task_id, run.condition_id, run.seed),
    )
    store = MemoryResultStore()
    EvaluationRunner(
        executor=FingerprintedExecutor(outcome, "model-a:prompt-a"),
        store=store,
    ).run([run])
    produced = EvaluationRunner(
        executor=FingerprintedExecutor(outcome, "model-b:prompt-a"),
        store=store,
    ).run([run])
    assert len(produced) == 1
    assert produced[0].attempt == 2


def test_final_gate_requires_all_current_pilot_runs_and_runtime_metadata() -> None:
    manifest = load_manifest(PILOT_MANIFEST)
    store = MemoryResultStore()
    with pytest.raises(RuntimeError, match="24 pilot"):
        validate_pilot_gate(store, manifest)
    for run in manifest:
        executor = StaticExecutor(
            ExecutionOutcome(
                terminal_reason="COMPLETED",
                final_state=success_state(run.task_id, run.condition_id, run.seed),
                runtime_metadata={
                    "model_id": "test-model",
                    "prompt_hash": "a" * 64,
                    "browser_version": "Chromium test",
                },
            )
        )
        EvaluationRunner(executor=executor, store=store).run([run])
    validate_pilot_gate(store, manifest)


def test_malformed_oracle_contract_is_infrastructure_not_agent_failure() -> None:
    run = _one_ready_run()
    executor = StaticExecutor(
        ExecutionOutcome(
            terminal_reason="COMPLETED",
            oracle_result={"pass": "yes"},
        )
    )
    result = EvaluationRunner(
        executor=executor, store=MemoryResultStore(), infrastructure_retries=0
    ).run([run])[0]
    assert result.failure_class is FailureClass.INFRASTRUCTURE
    assert result.error_code == "ORACLE_RESULT_INVALID"


def test_report_excludes_infrastructure_from_agent_success_denominator(tmp_path: Path) -> None:
    runs = [
        run
        for run in load_manifest(PILOT_MANIFEST)
        if run.configuration is EvaluationConfiguration.B1
    ][:2]
    store = MemoryResultStore()
    successful = StaticExecutor(
        ExecutionOutcome(
            terminal_reason="COMPLETED",
            final_state=success_state(runs[0].task_id, runs[0].condition_id, runs[0].seed),
        )
    )
    EvaluationRunner(executor=successful, store=store).run([runs[0]])
    failed = StaticExecutor(
        ExecutionOutcome(
            terminal_reason="INFRASTRUCTURE_ERROR",
            infrastructure_error="database unavailable",
        )
    )
    EvaluationRunner(executor=failed, store=store, infrastructure_retries=0).run([runs[1]])
    summary = build_summary(store.all_results())
    assert sum(row["analyzable_runs"] for row in summary["groups"]) == 1
    assert summary["infrastructure_failures"] == 1
    paths = write_reports(store.all_results(), tmp_path)
    assert all(path.exists() for path in paths.values())
    assert json.loads(paths["summary_json"].read_text(encoding="utf-8"))["latest_runs"] == 2


def test_report_contains_paired_comparison_and_domain_breakdown() -> None:
    pair = load_manifest(PILOT_MANIFEST)[:3]
    store = MemoryResultStore()
    for run in pair:
        final_state = (
            reset_case(run.task_id, run.condition_id, run.seed)["state"]
            if run.configuration is EvaluationConfiguration.B0
            else success_state(run.task_id, run.condition_id, run.seed)
        )
        EvaluationRunner(
            executor=StaticExecutor(
                ExecutionOutcome(terminal_reason="COMPLETED", final_state=final_state)
            ),
            store=store,
        ).run([run])
    summary = build_summary(store.all_results())
    b0_p = next(
        row
        for row in summary["paired_comparisons"]
        if row["left"] == "B0" and row["right"] == "P"
    )
    assert b0_p["complete_pairs"] == 1
    assert b0_p["right_only_success"] == 1
    assert summary["by_domain"][0]["domain"] == "travel"


def test_evaluation_migration_has_typed_result_table_and_rollback() -> None:
    migration_dir = ROOT / "packages/agent/migrations"
    up = (migration_dir / "004_evaluation_runs_up.sql").read_text(encoding="utf-8")
    down = (migration_dir / "004_evaluation_runs_down.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS evaluation_runs" in up
    assert "failure_class" in up and "oracle_success" in up and "result_payload" in up
    assert "PRIMARY KEY (manifest_run_id, attempt)" in up
    assert "DROP TABLE IF EXISTS evaluation_runs" in down


def test_pilot_pages_render_apply_and_score_without_exposing_oracle() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        reset = client.post(
            "/api/benchmark/reset",
            json={"task_id": "P04", "condition_id": "C1", "seed": 123},
        )
        assert reset.status_code == 200
        session_id = reset.json()["session_id"]
        page = client.get(reset.json()["start_url"])
        assert page.status_code == 200
        assert "Zona waktu draft" in page.text
        applied = client.post(
            f"/api/benchmark/sessions/{session_id}/actions",
            content="timezone=Asia%2FJakarta",
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=True,
        )
        assert applied.status_code == 200
        unauthorized = client.get(f"/internal/evaluation/sessions/{session_id}/oracle")
        assert unauthorized.status_code == 401
        oracle = client.get(
            f"/internal/evaluation/sessions/{session_id}/oracle",
            headers={"authorization": "Bearer test-secret"},
        )
        assert oracle.status_code == 200
        assert oracle.json()["pass"] is True


@pytest.mark.parametrize(
    ("task_id", "values"),
    [
        ("P01", {"route_id": "ptr1"}),
        ("P02", {"item_a": "on", "item_b": "on"}),
        ("P03", {"slot_id": "pap1"}),
        ("P04", {"timezone": "Asia/Jakarta"}),
    ],
)
@pytest.mark.parametrize("condition_id", ["C0", "C1", "C2"])
def test_all_pilot_pages_apply_success_state_for_each_condition(
    task_id: str, condition_id: str, values: dict[str, str]
) -> None:
    app = create_app(_settings())
    reset = app.state.case_store.reset(task_id, condition_id, 123)
    app.state.case_store.apply_action(reset["session_id"], values)
    from a11y_benchmark.oracles.engine import evaluate

    result = evaluate(task_id, app.state.case_store.private_state(reset["session_id"]))
    assert result["pass"] is True


def test_visual_model_receives_image_and_validates_coordinate_schema() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "action_type": "click",
                                            "x": 120,
                                            "y": 240,
                                            "expected_visual_effect": "Pilihan berubah.",
                                            "reason": "Kontrol terlihat pada screenshot.",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    model = GeminiVisualClient(
        "key",
        model="visual-test",
        fallback_model=None,
        max_retries=0,
        base_url="https://unit.test/v1beta",
        transport=httpx.MockTransport(handler),
    )
    screenshot = Screenshot(
        image_base64="aGVsbG8tdmlzdWFsLWltYWdl",
        mime_type="image/jpeg",
        width=800,
        height=600,
        url="http://127.0.0.1/task",
    )
    try:
        decision = model.decide({"goal": "Pilih item"}, screenshot)
    finally:
        model.close()
    assert (decision.x, decision.y) == (120, 240)
    parts = captured["contents"][0]["parts"]
    assert parts[1]["inlineData"]["data"] == screenshot.image_base64
    assert "responseJsonSchema" in captured["generationConfig"]


def test_visual_bridge_never_calls_semantic_endpoints() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/page/screenshot":
            return httpx.Response(
                200,
                json={
                    "image_base64": "aGVsbG8tdmlzdWFsLWltYWdl",
                    "mime_type": "image/jpeg",
                    "width": 800,
                    "height": 600,
                    "url": "http://127.0.0.1/task",
                },
            )
        if request.url.path == "/page/action":
            assert json.loads(request.content) == {"op": "coordinate_click", "x": 10, "y": 20}
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404)

    bridge = VisualBridge(
        "http://bridge.test",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        bridge.screenshot()
        from evaluation.visual_baseline import VisualDecision

        bridge.act(
            VisualDecision(
                action_type="click",
                x=10,
                y=20,
                expected_visual_effect="Kontrol berubah.",
                reason="Terlihat.",
            )
        )
    finally:
        bridge.close()
    assert paths == ["/page/screenshot", "/page/action"]
    assert all("aria" not in path and "locator" not in path for path in paths)


def test_visual_baseline_stops_on_done_without_semantic_oracle_access() -> None:
    class DoneModel:
        def decide(self, request, screenshot):
            from evaluation.visual_baseline import VisualDecision

            return VisualDecision(
                action_type="done",
                expected_visual_effect="Tujuan terlihat selesai.",
                reason="Status akhir terlihat.",
            )

    class ScreenshotOnlyBridge:
        def __init__(self):
            self.actions = 0

        def screenshot(self):
            return Screenshot(
                image_base64="aGVsbG8tdmlzdWFsLWltYWdl",
                mime_type="image/jpeg",
                width=800,
                height=600,
                url="http://127.0.0.1/task",
            )

        def act(self, decision):
            self.actions += 1

    bridge = ScreenshotOnlyBridge()
    outcome = VisualBaselineRunner(bridge=bridge, model=DoneModel()).run(
        goal="Pilih item",
        forbidden_actions=["checkout"],
        completion_boundary="Berhenti setelah draft.",
        max_steps=3,
    )
    assert outcome.agent_claimed_success
    assert outcome.step_count == 0
    assert bridge.actions == 0


def test_visual_baseline_propagates_bridge_transport_failure_as_infrastructure() -> None:
    class ClickModel:
        def decide(self, request, screenshot):
            from evaluation.visual_baseline import VisualDecision

            return VisualDecision(
                action_type="click",
                x=10,
                y=20,
                expected_visual_effect="Kontrol berubah.",
                reason="Tombol terlihat.",
            )

    class OfflineBridge:
        def screenshot(self):
            return Screenshot(
                image_base64="aGVsbG8tdmlzdWFsLWltYWdl",
                mime_type="image/jpeg",
                width=800,
                height=600,
                url="http://127.0.0.1/task",
            )

        def act(self, decision):
            request = httpx.Request("POST", "http://bridge.test/page/action")
            raise httpx.ConnectError("bridge unavailable", request=request)

    with pytest.raises(httpx.ConnectError):
        VisualBaselineRunner(bridge=OfflineBridge(), model=ClickModel()).run(
            goal="Pilih item",
            forbidden_actions=["checkout"],
            completion_boundary="Berhenti setelah draft.",
            max_steps=3,
        )
