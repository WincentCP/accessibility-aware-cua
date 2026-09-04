from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.agent.privacy import REDACTED, contains_forbidden_material, redact_payload
from backend.agent.retention import RetentionPolicy


def test_secret_values_are_masked_and_raw_audio_is_dropped() -> None:
    payload = {
        "password": "Rahasia123",
        "nested": {
            "api_key": "sk-private-value",
            "note": "otp=918273 and Bearer abc.def.ghi",
            "raw_audio": "base64-private-audio",
        },
    }
    cleaned = redact_payload(payload)
    serialized = repr(cleaned)
    assert cleaned["password"] == REDACTED
    assert cleaned["nested"]["api_key"] == REDACTED
    assert "918273" not in serialized
    assert "abc.def.ghi" not in serialized
    assert "base64-private-audio" not in serialized
    assert not contains_forbidden_material(cleaned)


def test_binary_payload_never_reaches_storage() -> None:
    assert redact_payload(b"voice bytes") == REDACTED


def test_retention_policy_has_enforced_zero_day_sensitive_classes() -> None:
    policy = RetentionPolicy()
    assert policy.raw_audio_days == 0
    assert policy.secret_days == 0
    assert policy.audit_cutoff(datetime(2026, 8, 25, tzinfo=UTC)).isoformat().startswith(
        "2026-05-27"
    )
    with pytest.raises(ValidationError):
        RetentionPolicy(raw_audio_days=1)
