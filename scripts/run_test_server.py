#!/usr/bin/env python3
"""Start a deterministic test-only API for Playwright."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["CUA_ENV"] = "test"
os.environ["CUA_APP_SECRET"] = "stage5-test-secret-not-for-production"
os.environ["CUA_REQUIRE_POSTGRES"] = "false"

import uvicorn  # noqa: E402

from backend.api.app import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8015, log_level="warning")
