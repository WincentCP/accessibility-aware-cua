from __future__ import annotations

from uuid import uuid4

from pydantic import ValidationError

from packages.agent.contracts import (
    AgentAction,
    Observation,
    RelevantItem,
    VerificationResult,
)
from packages.agent.task_map import (
    DisplayStatus,
    TaskMapCompileInput,
    TaskMapCompiler,
    TaskMapItem,
)


def observation(version: int = 3) -> Observation:
    return Observation(version=version, url="http://127.0.0.1/task", nodes=[])


def test_completed_claims_require_verified_evidence_and_provenance() -> None:
    before, after = uuid4(), uuid4()
    verified_step = uuid4()
    failed_step = uuid4()
    source = TaskMapCompileInput(
        session_id=uuid4(),
        run_id=uuid4(),
        version=2,
        goal="Cari pilihan paling murah tanpa melakukan pemesanan.",
        observation=observation(),
        verifications=[
            VerificationResult(
                step_id=verified_step,
                status="VERIFIED",
                evidence=["Status hasil berubah menjadi dipilih"],
                before_observation_ref=before,
                after_observation_ref=after,
            ),
            VerificationResult(
                step_id=failed_step,
                status="FAILED",
                evidence=["Hasil belum berubah"],
                before_observation_ref=before,
                after_observation_ref=after,
            ),
        ],
        effect_by_step_id={
            str(verified_step): "Hasil termurah dipilih",
            str(failed_step): "Filter harga diterapkan",
        },
    )
    result = TaskMapCompiler().compile(source)
    assert [item.label for item in result.verified_completed] == ["Hasil termurah dipilih"]
    assert result.verified_completed[0].verification_id is not None
    assert result.verified_completed[0].evidence
    assert [item.label for item in result.uncertain_items] == ["Filter harga diterapkan"]
    assert result.uncertain_items[0].status is DisplayStatus.UNCERTAIN


def test_stale_relevant_items_and_plans_are_invalidated() -> None:
    source = TaskMapCompileInput(
        session_id=uuid4(),
        run_id=uuid4(),
        version=4,
        goal="Pilih hasil.",
        observation=observation(version=5),
        relevant_items=[
            RelevantItem(
                semantic_ref="v4:ax0001",
                label="Pilihan lama",
                reason="Dari snapshot lama",
                observation_version=4,
            ),
            RelevantItem(
                semantic_ref="v5:ax0002",
                label="Pilihan baru",
                reason="Cocok dengan tujuan",
                observation_version=5,
            ),
        ],
        planned_action=AgentAction(
            action_type="click",
            target_ref="v4:ax0001",
            observation_version=4,
            expected_effect="Aktifkan pilihan lama",
        ),
    )
    result = TaskMapCompiler().compile(source)
    assert [item.label for item in result.relevant_options] == ["Pilihan baru"]
    assert result.next_action is None
    assert result.stale_invalidated_count == 2


def test_fresh_plan_is_visibly_separate_from_completed_claims() -> None:
    source = TaskMapCompileInput(
        session_id=uuid4(),
        run_id=uuid4(),
        version=1,
        goal="Buka detail.",
        observation=observation(version=2),
        planned_action=AgentAction(
            action_type="click",
            target_ref="v2:ax0001",
            observation_version=2,
            expected_effect="Detail akan dibuka",
        ),
    )
    result = TaskMapCompiler().compile(source)
    assert result.verified_completed == []
    assert result.next_action is not None
    assert result.next_action.status is DisplayStatus.PLANNED
    assert "terverifikasi" in result.progress_label


def test_contract_rejects_completed_claim_without_evidence() -> None:
    try:
        TaskMapItem(
            label="Tidak boleh dipercaya",
            status="VERIFIED_COMPLETED",
            observation_version=1,
            verification_id=uuid4(),
        )
    except ValidationError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("Completed claim tanpa evidence seharusnya ditolak")
