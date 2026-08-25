"""Typed, deterministic postconditions for verify-after-action."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from packages.agent.contracts import ClosedModel, VerificationStatus, utc_now


class PredicateKind(StrEnum):
    URL = "url"
    TITLE = "title"
    FIELD_VALUE = "field_value"
    ELEMENT_STATE = "element_state"
    ELEMENT_PRESENCE = "element_presence"
    TEXT = "text"
    DIALOG_STATE = "dialog_state"
    CART_COUNT = "cart_count"
    BACKEND_STATE = "backend_state"


class MatchMode(StrEnum):
    EQUALS = "equals"
    CONTAINS = "contains"


class ExpectedPostcondition(ClosedModel):
    predicate_id: UUID = Field(default_factory=uuid4)
    kind: PredicateKind
    expected: str | bool | int
    role: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, max_length=1_000)
    state_key: str | None = Field(default=None, max_length=128)
    match: MatchMode = MatchMode.EQUALS

    @model_validator(mode="after")
    def validate_target(self) -> ExpectedPostcondition:
        if (
            self.kind
            in {
                PredicateKind.FIELD_VALUE,
                PredicateKind.ELEMENT_STATE,
                PredicateKind.ELEMENT_PRESENCE,
                PredicateKind.TEXT,
                PredicateKind.DIALOG_STATE,
                PredicateKind.CART_COUNT,
            }
            and not self.role
        ):
            raise ValueError(f"role wajib untuk predicate {self.kind.value}")
        if self.kind is PredicateKind.ELEMENT_STATE and not self.state_key:
            raise ValueError("state_key wajib untuk element_state")
        if self.kind is PredicateKind.BACKEND_STATE and not self.name:
            raise ValueError("name adalah key untuk backend_state")
        return self


class VerificationPlan(ClosedModel):
    step_id: UUID
    before_observation_ref: UUID
    predicates: list[ExpectedPostcondition] = Field(min_length=1, max_length=16)
    planned_at: datetime = Field(default_factory=utc_now)


class PredicateEvidence(ClosedModel):
    predicate_id: UUID
    status: VerificationStatus
    expected_summary: str
    observed_summary: str
    evidence_ref: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


def safe_summary(value: Any, *, sensitive: bool = False) -> str:
    if sensitive:
        digest = hashlib.sha256(str(value).encode()).hexdigest()[:12]
        return f"redacted(len={len(str(value))},sha256={digest})"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def evidence_ref(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
