"""Verify expected postconditions from fresh accessibility observations."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from packages.agent.contracts import (
    ErrorCode,
    Observation,
    VerificationResult,
    VerificationStatus,
)
from packages.agent.observer import AccessibilityObserver
from packages.agent.predicates import (
    ExpectedPostcondition,
    MatchMode,
    PredicateEvidence,
    PredicateKind,
    VerificationPlan,
    evidence_ref,
    safe_summary,
)


class PredicateVerifier:
    """Deterministic verifier; planner claims are never accepted as evidence."""

    def __init__(self, observer: AccessibilityObserver | None = None) -> None:
        self.observer = observer or AccessibilityObserver()

    @staticmethod
    def _nodes(observation: Observation, predicate: ExpectedPostcondition):
        return [
            node
            for node in observation.nodes
            if node.role == predicate.role and (predicate.name is None or node.name == predicate.name)
        ]

    def evaluate(
        self,
        predicate: ExpectedPostcondition,
        observation: Observation,
        *,
        backend_state: dict[str, Any] | None = None,
    ) -> PredicateEvidence:
        sensitive = predicate.kind is PredicateKind.FIELD_VALUE
        expected = predicate.expected
        observed: Any = None
        determinate = True

        if predicate.kind is PredicateKind.URL:
            observed = observation.url
        elif predicate.kind is PredicateKind.TITLE:
            observed = observation.title
        elif predicate.kind is PredicateKind.BACKEND_STATE:
            if backend_state is None or predicate.name not in backend_state:
                determinate = False
            else:
                observed = backend_state[predicate.name]
        else:
            matches = self._nodes(observation, predicate)
            if predicate.kind in {
                PredicateKind.ELEMENT_PRESENCE,
                PredicateKind.DIALOG_STATE,
            }:
                observed = bool(matches)
            elif len(matches) != 1:
                determinate = False
                observed = f"matches={len(matches)}"
            else:
                node = matches[0]
                if predicate.kind is PredicateKind.FIELD_VALUE:
                    observed = node.value_summary
                elif predicate.kind is PredicateKind.ELEMENT_STATE:
                    observed = getattr(node, predicate.state_key, None)
                    if observed is None:
                        observed = node.states.get(predicate.state_key or "")
                    if observed is None:
                        determinate = False
                elif predicate.kind is PredicateKind.TEXT:
                    observed = node.name
                elif predicate.kind is PredicateKind.CART_COUNT:
                    digits = "".join(character for character in node.name if character.isdigit())
                    if not digits:
                        determinate = False
                    else:
                        observed = int(digits)

        if not determinate:
            status = VerificationStatus.UNCERTAIN
        elif predicate.match is MatchMode.CONTAINS:
            status = (
                VerificationStatus.VERIFIED
                if str(expected).casefold() in str(observed).casefold()
                else VerificationStatus.FAILED
            )
        else:
            status = VerificationStatus.VERIFIED if observed == expected else VerificationStatus.FAILED
        expected_summary = safe_summary(expected, sensitive=sensitive)
        observed_summary = safe_summary(observed, sensitive=sensitive)
        ref = evidence_ref(
            {
                "predicate_id": predicate.predicate_id,
                "kind": predicate.kind,
                "status": status,
                "expected": expected_summary,
                "observed": observed_summary,
                "observation_ref": observation.observation_ref,
            }
        )
        return PredicateEvidence(
            predicate_id=predicate.predicate_id,
            status=status,
            expected_summary=expected_summary,
            observed_summary=observed_summary,
            evidence_ref=ref,
        )

    def verify(
        self,
        page: Any,
        plan: VerificationPlan,
        *,
        execution_started_at: datetime,
        backend_state: dict[str, Any] | None = None,
        timeout_ms: int = 750,
        poll_ms: int = 100,
    ) -> tuple[VerificationResult, list[PredicateEvidence]]:
        if plan.planned_at > execution_started_at:
            raise ValueError("Postcondition wajib dibuat sebelum eksekusi dimulai")
        deadline = time.monotonic() + timeout_ms / 1_000
        evidence: list[PredicateEvidence] = []
        observation: Observation | None = None
        while True:
            observation = self.observer.capture(page)
            evidence = [
                self.evaluate(predicate, observation, backend_state=backend_state)
                for predicate in plan.predicates
            ]
            if all(item.status is VerificationStatus.VERIFIED for item in evidence):
                status = VerificationStatus.VERIFIED
                break
            if time.monotonic() >= deadline:
                status = (
                    VerificationStatus.FAILED
                    if any(item.status is VerificationStatus.FAILED for item in evidence)
                    else VerificationStatus.UNCERTAIN
                )
                break
            page.wait_for_timeout(poll_ms)

        assert observation is not None
        result = VerificationResult(
            step_id=plan.step_id,
            status=status,
            evidence=[item.evidence_ref for item in evidence],
            before_observation_ref=plan.before_observation_ref,
            after_observation_ref=observation.observation_ref,
            error_code=(
                ErrorCode.NONE if status is VerificationStatus.VERIFIED else ErrorCode.VERIFICATION_FAILED
            ),
        )
        return result, evidence
