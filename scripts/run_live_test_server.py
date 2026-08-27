"""Run the API with the isolated, key-free planner used by automated Chromium QA."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.update(
    {
        "CUA_ENV": "test",
        "CUA_APP_SECRET": "local-test-agent-secret-2026-safe",
        "CUA_HOST": "127.0.0.1",
        "CUA_PORT": "8000",
        "CUA_REQUIRE_POSTGRES": "false",
        "CUA_BROWSER_BRIDGE_URL": "http://127.0.0.1:8765",
        "CUA_PLANNER_PROVIDER": "deterministic",
        "CUA_PLANNER_MODEL": "deterministic-t01-v1",
        "CUA_LIVE_AGENT_ENABLED": "true",
        "CUA_TTS_ENABLED": "false",
    }
)

if __name__ == "__main__":
    uvicorn.run("apps.api.a11y_api.app:create_app", host="127.0.0.1", port=8000, factory=True)
