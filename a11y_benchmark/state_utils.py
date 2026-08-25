"""Small dependency-free helpers for nested benchmark state."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

MISSING = object()


def get_path(data: dict, path: str, default: Any = MISSING) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            if default is MISSING:
                raise KeyError(path)
            return default
        current = current[part]
    return current


def set_path(data: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = deepcopy(value)


def apply_patch(state: dict, patch: dict) -> dict:
    result = deepcopy(state)
    for path, value in patch.items():
        set_path(result, path, value)
    return result


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_int(text: str, digits: int = 9) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:15], 16) % (10**digits)
