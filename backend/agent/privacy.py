"""Central redaction policy applied before every database or log write."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"
DROP_KEY_FRAGMENTS = ("raw_audio", "audio_blob", "audio_bytes", "waveform")
SECRET_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "passcode",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "cookie",
    "secret",
    "token",
    "otp",
)
TEXT_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:password|passwd|passcode|otp|api[_ -]?key)\s*[:=]\s*)\S+"),
)


def _clean_text(value: str) -> str:
    cleaned = value
    for pattern in TEXT_PATTERNS:
        cleaned = pattern.sub(r"\1[REDACTED]", cleaned)
    return cleaned


def redact_payload(value: Any) -> Any:
    """Return JSON-compatible data with raw audio dropped and secrets masked."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, nested in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("-", "_")
            if any(fragment in normalized for fragment in DROP_KEY_FRAGMENTS):
                continue
            if any(fragment in normalized for fragment in SECRET_KEY_FRAGMENTS):
                result[key] = REDACTED
            else:
                result[key] = redact_payload(nested)
        return result
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [redact_payload(item) for item in value]
    if isinstance(value, bytes | bytearray | memoryview):
        return REDACTED
    return value


def contains_forbidden_material(value: Any) -> bool:
    """Conservative assertion helper used by tests and adapters."""

    serialized = repr(value).lower()
    return any(fragment in serialized for fragment in DROP_KEY_FRAGMENTS)
