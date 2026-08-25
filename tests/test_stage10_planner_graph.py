from __future__ import annotations

import re
import time
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from playwright.sync_api import sync_playwright

from packages.agent.executor import DeterministicExecutor
from packages.agent.graph import (
    GraphRoute,
    OrchestrationServices,
    apply_correction_to_state,
    build_agent_graph,
)
from packages.agent.observer import AccessibilityObserver
from packages.agent.planner import (
    ModelResponse,
    PlannerConfig,
    PlannerRequest,
    StructuredPlanner,
    clarify_if_needed,
    normalize_input,
)
from packages.agent.recovery import RecoveryController
from packages.agent.resolver import SemanticTargetResolver
from packages.agent.verifier import PredicateVerifier


class GenericPilotModel:
    """Structured model test double; derives targets from AX input, never task IDs."""

    def __init__(
        self, *, malformed_first: bool = False, always_invalid: bool = False, high_risk: bool = False
    ):
        self.calls = 0
        self.malformed_first = malformed_first
        self.always_invalid = always_invalid
        self.high_risk = high_risk
        self.requests = []

    def generate(self, *, prompt, schema, request):
        self.calls += 1
        self.requests.append(request)
        if self.always_invalid or (self.malformed_first and self.calls == 1):
            payload = {"not": "the schema"}
        else:
            observation = request["compact_observation"]
            target = re.search(r"\[(v\d+:ax\d+)\] button \"([^\"]+)\"", observation)
            assert target is not None
            version = int(target.group(1).split(":")[0][1:])
            payload = {
                "action": {
                    "action_type": "click",
                    "target_ref": target.group(1),
                    "observation_version": version,
                    "expected_effect": "Status tugas berubah menjadi Selesai",
                    "risk_level": "HIGH" if self.high_risk else "LOW",
                    "requires_approval": self.high_risk,
                },
                "postconditions": [{"kind": "text", "role": "status", "expected": "Selesai"}],
                "reason": "Aktifkan kontrol semantik yang tersedia.",
                "goal_complete_after_verification": True,
            }
        return ModelResponse(
            payload=payload,
            input_tokens=40,
            output_tokens=30,
            model_id="structured-pilot-model",
            provider="test-double",
            latency_ms=2,
        )


class RecoveringPilotModel(GenericPilotModel):
    def __init__(self, fault: str):
        super().__init__()
        self.fault = fault

    def generate(self, *, prompt, schema, request):
        response = super().generate(prompt=prompt, schema=schema, request=request)
        if self.calls == 1 and self.fault == "wrong_postcondition":
            response.payload["postconditions"][0]["expected"] = "Tidak pernah terjadi"
        if self.calls == 1 and self.fault == "stale_target":
            response.payload["action"]["target_ref"] = "v1:ax9999"
        return response


def request_for(goal_text="Pilih hasil yang valid dan jangan melakukan pembayaran"):
    return PlannerRequest(
        compact_observation='- [v1:ax0001] button "Lanjut"',
        goal=normalize_input(goal_text),
        remaining_steps=5,
        remaining_tokens=2_000,
    )


def test_goal_normalization_and_material_clarification() -> None:
    goal = normalize_input("Pilih rute termurah; maksimal Rp900.000; jangan booking.")
    assert goal.constraints
    assert goal.forbidden_actions == ["jangan booking"]
    assert "jangan booking" in goal.completion_boundary
    assert clarify_if_needed(goal) is None
    assert clarify_if_needed(normalize_input("lanjut")) is not None


def test_schema_error_gets_exactly_one_controlled_retry() -> None:
    model = GenericPilotModel(malformed_first=True)
    decision, telemetry = StructuredPlanner(model).plan(request_for())
    assert decision.action.action_type.value == "click"
    assert model.calls == 2
    assert telemetry.schema_attempts == 2
    assert "schema_correction" not in model.requests[0]
    assert "schema_correction" in model.requests[1]


def test_malformed_output_aborts_after_one_retry() -> None:
    model = GenericPilotModel(always_invalid=True)
    with pytest.raises(RuntimeError, match="after controlled retry"):
        StructuredPlanner(model).plan(request_for())
    assert model.calls == 2


def test_step_and_token_budgets_are_hard_limits() -> None:
    planner = StructuredPlanner(GenericPilotModel())
    with pytest.raises(RuntimeError, match="step budget"):
        planner.plan(request_for().model_copy(update={"remaining_steps": 0}))
    with pytest.raises(RuntimeError, match="token budget"):
        planner.plan(request_for().model_copy(update={"remaining_tokens": 1}))


def services(page, model):
    observer = AccessibilityObserver()
    return OrchestrationServices(
        page=page,
        observer=observer,
        executor=DeterministicExecutor(SemanticTargetResolver(observer.registry)),
        verifier=PredicateVerifier(),
        planner=StructuredPlanner(model, PlannerConfig(task_token_budget=5_000)),
        recovery=RecoveryController(),
    )


def initial_state(index: int):
    return {
        "schema_version": "1.0.0",
        "session_id": str(uuid4()),
        "thread_id": f"pilot:{index}:{uuid4()}",
        "run_id": str(uuid4()),
        "task_id": f"T{index + 1:02d}",
        "raw_input": "Aktifkan kontrol tugas lalu berhenti ketika status selesai; jangan bayar.",
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


def test_five_cross_site_pilots_complete_without_task_specific_branching() -> None:
    labels = ["Travel", "Travel", "Marketplace", "Appointment", "Account"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        trajectories = []
        for index, label in enumerate(labels):
            page = browser.new_page()
            page.set_content(
                f'<main><h1>{label}</h1><button onclick="s.textContent=\'Selesai\'">Jalankan tugas</button><p id="s" role="status">Menunggu</p></main>'
            )
            model = GenericPilotModel()
            graph = build_agent_graph(services(page, model), checkpointer=InMemorySaver())
            state = initial_state(index)
            result = graph.invoke(state, {"configurable": {"thread_id": state["thread_id"]}})
            assert result["terminal_reason"] == "COMPLETED"
            assert result["verification"]["status"] == "VERIFIED"
            assert result["step_count"] == 1
            assert len(result["verified_progress"]) == 1
            assert model.calls == 1
            trajectories.append(result)
            page.close()
        browser.close()
    assert len(trajectories) == 5


def test_interrupt_checkpoint_restores_task_map_and_handoff_state() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content('<main><button>Jalankan</button><p role="status">Menunggu</p></main>')
        saver = InMemorySaver()
        state = initial_state(0)
        config = {"configurable": {"thread_id": state["thread_id"]}}
        first = build_agent_graph(services(page, GenericPilotModel(high_risk=True)), checkpointer=saver)
        result = first.invoke(state, config)
        assert result["pending_interrupt"]["kind"] == "APPROVAL"
        assert result["handoff_status"] == "REQUESTED"
        restarted = build_agent_graph(services(page, GenericPilotModel()), checkpointer=saver)
        snapshot = restarted.get_state(config)
        assert snapshot.values["task_map_version"] == result["task_map_version"]
        assert snapshot.values["handoff_status"] == "REQUESTED"
        assert snapshot.values["thread_id"] == state["thread_id"]
        browser.close()


@pytest.mark.parametrize("fault", ["wrong_postcondition", "stale_target"])
def test_two_failure_scenarios_replan_from_fresh_observation(fault) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<main><button onclick="s.textContent=\'Selesai\'">Jalankan</button><p id="s" role="status">Menunggu</p></main>'
        )
        model = RecoveringPilotModel(fault)
        graph = build_agent_graph(services(page, model))
        result = graph.invoke(initial_state(0))
        assert result["terminal_reason"] == "COMPLETED"
        assert result["verification"]["status"] == "VERIFIED"
        assert result["recovery_count"] == 1
        assert model.calls == 2
        browser.close()


def test_conditional_route_rejects_free_text() -> None:
    with pytest.raises(ValueError):
        GraphRoute("planner says maybe execute")


def test_user_correction_updates_constraints_without_new_session() -> None:
    state = initial_state(0)
    state["normalized_goal"] = normalize_input(state["raw_input"]).model_dump(mode="json")
    session_id, thread_id, run_id = state["session_id"], state["thread_id"], state["run_id"]
    update = apply_correction_to_state(state, "Cari yang lebih murah dan jangan submit.")
    assert "lebih murah" in update["normalized_goal"]["objective"]
    assert any("jangan submit" in item.casefold() for item in update["normalized_goal"]["forbidden_actions"])
    merged = {**state, **update}
    assert (merged["session_id"], merged["thread_id"], merged["run_id"]) == (session_id, thread_id, run_id)
