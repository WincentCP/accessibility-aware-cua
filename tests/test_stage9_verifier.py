from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from playwright.sync_api import sync_playwright
from pydantic import ValidationError

from backend.agent.contracts import (
    ErrorCode,
    RiskLevel,
    TerminalReason,
    VerificationStatus,
)
from backend.agent.executor import DeterministicExecutor, PrimitiveAction, PrimitiveActionRequest
from backend.agent.observer import AccessibilityObserver
from backend.agent.predicates import (
    ExpectedPostcondition,
    PredicateKind,
    VerificationPlan,
)
from backend.agent.recovery import (
    CompletedClaim,
    HiddenOracleVerdict,
    RecoveryContext,
    RecoveryController,
    RecoveryDecision,
    RecoveryPolicy,
    final_success_from_hidden_oracle,
)
from backend.agent.resolver import SemanticTargetResolver
from backend.agent.verifier import PredicateVerifier


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    page.set_content(
        """
        <main>
          <h1>Review Pesanan</h1>
          <label>Nama <input value="Budi"></label>
          <label><input type="checkbox" checked> Setuju</label>
          <button aria-expanded="true">Detail</button>
          <p role="status">Keranjang berisi 2 barang</p>
          <div role="dialog" aria-label="Konfirmasi">Siap</div>
        </main>
        """
    )
    yield page
    page.close()


def observation(page):
    return AccessibilityObserver().capture(page)


@pytest.mark.parametrize(
    ("predicate", "backend"),
    [
        (ExpectedPostcondition(kind="url", expected="about:blank"), None),
        (ExpectedPostcondition(kind="title", expected=""), None),
        (ExpectedPostcondition(kind="field_value", role="textbox", name="Nama", expected="Budi"), None),
        (
            ExpectedPostcondition(
                kind="element_state", role="checkbox", name="Setuju", state_key="checked", expected=True
            ),
            None,
        ),
        (ExpectedPostcondition(kind="element_presence", role="button", name="Detail", expected=True), None),
        (ExpectedPostcondition(kind="text", role="status", expected="2 barang", match="contains"), None),
        (ExpectedPostcondition(kind="dialog_state", role="dialog", name="Konfirmasi", expected=True), None),
        (ExpectedPostcondition(kind="cart_count", role="status", expected=2), None),
        (ExpectedPostcondition(kind="backend_state", name="phase", expected="review"), {"phase": "review"}),
    ],
)
def test_each_predicate_true(page, predicate, backend) -> None:
    result = PredicateVerifier().evaluate(predicate, observation(page), backend_state=backend)
    assert result.status is VerificationStatus.VERIFIED
    assert result.evidence_ref.startswith("sha256:")


@pytest.mark.parametrize(
    ("predicate", "backend"),
    [
        (ExpectedPostcondition(kind="url", expected="https://wrong.invalid"), None),
        (ExpectedPostcondition(kind="title", expected="Wrong"), None),
        (ExpectedPostcondition(kind="field_value", role="textbox", name="Nama", expected="Salah"), None),
        (
            ExpectedPostcondition(
                kind="element_state", role="checkbox", name="Setuju", state_key="checked", expected=False
            ),
            None,
        ),
        (ExpectedPostcondition(kind="element_presence", role="button", name="Hilang", expected=True), None),
        (ExpectedPostcondition(kind="text", role="status", expected="kosong", match="contains"), None),
        (ExpectedPostcondition(kind="dialog_state", role="dialog", name="Hilang", expected=True), None),
        (ExpectedPostcondition(kind="cart_count", role="status", expected=9), None),
        (ExpectedPostcondition(kind="backend_state", name="phase", expected="done"), {"phase": "review"}),
    ],
)
def test_each_predicate_false(page, predicate, backend) -> None:
    result = PredicateVerifier().evaluate(predicate, observation(page), backend_state=backend)
    assert result.status is VerificationStatus.FAILED


@pytest.mark.parametrize(
    ("predicate", "backend"),
    [
        (ExpectedPostcondition(kind="field_value", role="textbox", name="Tidak ada", expected="x"), None),
        (
            ExpectedPostcondition(
                kind="element_state", role="button", name="Detail", state_key="selected", expected=True
            ),
            None,
        ),
        (ExpectedPostcondition(kind="text", role="button", name=None, expected="Detail"), None),
        (ExpectedPostcondition(kind="cart_count", role="heading", name="Review Pesanan", expected=2), None),
        (ExpectedPostcondition(kind="backend_state", name="missing", expected="x"), {}),
    ],
)
def test_predicates_uncertain_when_evidence_insufficient(page, predicate, backend) -> None:
    if predicate.kind is PredicateKind.TEXT:
        page.set_content("<main><button>A</button><button>B</button></main>")
    result = PredicateVerifier().evaluate(predicate, observation(page), backend_state=backend)
    assert result.status is VerificationStatus.UNCERTAIN


def test_delayed_update_is_observed_before_failure(page) -> None:
    page.set_content(
        '<main><p role="status" id="s">Menunggu</p><script>setTimeout(()=>s.textContent="Selesai",150)</script></main>'
    )
    before = observation(page)
    step_id = uuid4()
    plan = VerificationPlan(
        step_id=step_id,
        before_observation_ref=before.observation_ref,
        predicates=[ExpectedPostcondition(kind="text", role="status", expected="Selesai")],
        planned_at=datetime.now(UTC) - timedelta(milliseconds=1),
    )
    result, evidence = PredicateVerifier().verify(
        page,
        plan,
        execution_started_at=datetime.now(UTC),
        timeout_ms=600,
        poll_ms=50,
    )
    assert result.status is VerificationStatus.VERIFIED
    assert evidence[0].status is VerificationStatus.VERIFIED


def test_noop_action_cannot_be_reported_as_success(page) -> None:
    page.set_content('<main><button id="noop">Simpan</button><p role="status">Belum disimpan</p></main>')
    observer = AccessibilityObserver()
    before = observer.capture(page)
    target_ref = next(node.node_id for node in before.nodes if node.role == "button")
    step_id = uuid4()
    plan = VerificationPlan(
        step_id=step_id,
        before_observation_ref=before.observation_ref,
        predicates=[ExpectedPostcondition(kind="text", role="status", expected="Tersimpan")],
        planned_at=datetime.now(UTC) - timedelta(milliseconds=1),
    )
    executor = DeterministicExecutor(SemanticTargetResolver(observer.registry))
    execution_started = datetime.now(UTC)
    execution = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            step_id=step_id,
            primitive=PrimitiveAction.ACTIVATE,
            target_ref=target_ref,
            observation_version=before.version,
        ),
    )
    verification, _ = PredicateVerifier().verify(
        page,
        plan,
        execution_started_at=execution_started,
        timeout_ms=0,
    )
    assert execution.success
    assert verification.status is VerificationStatus.FAILED


def test_postcondition_cannot_be_created_after_action(page) -> None:
    before = observation(page)
    plan = VerificationPlan(
        step_id=uuid4(),
        before_observation_ref=before.observation_ref,
        predicates=[ExpectedPostcondition(kind="url", expected="about:blank")],
        planned_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="sebelum eksekusi"):
        PredicateVerifier().verify(page, plan, execution_started_at=datetime.now(UTC))


def test_field_evidence_redacts_actual_value(page) -> None:
    secret = "rahasia-user-123"
    page.get_by_role("textbox", name="Nama").fill(secret)
    item = PredicateVerifier().evaluate(
        ExpectedPostcondition(kind="field_value", role="textbox", name="Nama", expected=secret),
        observation(page),
    )
    assert secret not in item.model_dump_json()
    assert "redacted" in item.observed_summary


def context(**updates):
    base = dict(
        step_id=uuid4(),
        verification_status=VerificationStatus.FAILED,
        recovery_cycle=0,
    )
    base.update(updates)
    return RecoveryContext(**base)


def test_recovery_ladder_is_bounded_and_auditable() -> None:
    controller = RecoveryController(RecoveryPolicy(max_recovery_cycles_per_action=2, max_replans_per_task=1))
    assert controller.decide(context(recovery_cycle=0)).decision is RecoveryDecision.WAIT_REOBSERVE
    assert controller.decide(context(recovery_cycle=1)).decision is RecoveryDecision.RETRY
    assert controller.decide(context(recovery_cycle=2, replan_count=0)).decision is RecoveryDecision.REPLAN
    assert controller.decide(context(recovery_cycle=2, replan_count=1)).decision is RecoveryDecision.ASK_USER


def test_sensitive_recovery_requires_fresh_approval() -> None:
    outcome = RecoveryController().decide(
        context(recovery_cycle=1, risk_level=RiskLevel.HIGH, requires_approval=True, approval_consumed=True)
    )
    assert outcome.decision is RecoveryDecision.ASK_USER
    assert outcome.approval_required


def test_stale_and_ambiguous_faults_reresolve_from_fresh_snapshot() -> None:
    for code in (ErrorCode.STALE_OBSERVATION, ErrorCode.TARGET_NOT_FOUND, ErrorCode.AMBIGUOUS_TARGET):
        assert (
            RecoveryController().decide(context(recovery_cycle=1, error_code=code)).decision
            is RecoveryDecision.RERESOLVE
        )


def test_global_limits_abort_without_loop() -> None:
    controller = RecoveryController(RecoveryPolicy(max_steps=3, max_runtime_ms=1_000))
    steps = controller.decide(context(step_count=3))
    runtime = controller.decide(context(runtime_ms=1_000))
    assert steps.decision is RecoveryDecision.ABORT
    assert steps.terminal_reason is TerminalReason.MAX_STEPS
    assert runtime.decision is RecoveryDecision.ABORT


def test_completed_claim_requires_verified_evidence(page) -> None:
    before = observation(page)
    plan = VerificationPlan(
        step_id=uuid4(),
        before_observation_ref=before.observation_ref,
        predicates=[ExpectedPostcondition(kind="url", expected="about:blank")],
        planned_at=datetime.now(UTC) - timedelta(milliseconds=1),
    )
    verified, _ = PredicateVerifier().verify(page, plan, execution_started_at=datetime.now(UTC), timeout_ms=0)
    CompletedClaim(item="halaman benar", verification=verified, evidence_ref=verified.evidence[0])
    failed = verified.model_copy(update={"status": VerificationStatus.FAILED})
    with pytest.raises(ValidationError):
        CompletedClaim(item="klaim palsu", verification=failed, evidence_ref=failed.evidence[0])


def test_final_success_uses_hidden_oracle_only() -> None:
    assert final_success_from_hidden_oracle(HiddenOracleVerdict(passed=True))
    assert not final_success_from_hidden_oracle(HiddenOracleVerdict(passed=False))
    with pytest.raises(ValidationError):
        HiddenOracleVerdict(source="planner_finish", passed=True)
