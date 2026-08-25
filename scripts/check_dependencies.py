#!/usr/bin/env python3
"""Fail-fast readiness gate for API, catalog, isolated browser config, and DB."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

load_dotenv(ROOT / ".env")
os.environ.setdefault("CUA_REQUIRE_POSTGRES", "true")

from apps.api.a11y_api.app import create_app  # noqa: E402
from apps.api.a11y_api.config import Settings  # noqa: E402


def main() -> int:
    client = TestClient(create_app(Settings.from_env()))
    response = client.get("/health/ready")
    print(response.json())
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
