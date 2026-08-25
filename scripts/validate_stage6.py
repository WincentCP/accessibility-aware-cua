#!/usr/bin/env python3
"""Machine-readable Stage 6 gate without generating repository reports."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.agent.contracts import AgentAction  # noqa: E402
from packages.agent.persistence import AuditRepository  # noqa: E402


def main() -> int:
    required_files = [
        "packages/agent/contracts.py",
        "packages/agent/state.py",
        "packages/agent/privacy.py",
        "packages/agent/checkpoints.py",
        "packages/agent/persistence.py",
        "packages/agent/retention.py",
        "packages/agent/migrations/001_stage6_up.sql",
        "packages/agent/migrations/001_stage6_down.sql",
        "apps/extension/src/contracts.ts",
        "docs/stage6_erd.md",
        "docs/stage6_data_dictionary.md",
        "docs/privacy_and_retention.md",
        "STAGE6_DOD.md",
    ]
    missing = [path for path in required_files if not (ROOT / path).is_file()]

    invalid_action_rejected = False
    try:
        AgentAction(
            action_type="click",
            observation_version=1,
            expected_effect="invalid because target is absent",
        )
    except ValueError:
        invalid_action_rejected = True

    postgres_required = os.getenv("CUA_REQUIRE_POSTGRES", "false").lower() == "true"
    postgres_gate: dict[str, object]
    if postgres_required:
        try:
            repository = AuditRepository(os.environ["DATABASE_URL"])
            with repository.connection() as connection:
                stage6_version = connection.execute(
                    "SELECT version FROM schema_migrations WHERE version = '001_stage6'"
                ).fetchone()
                checkpoint_table = connection.execute(
                    "SELECT to_regclass('public.checkpoints') AS name"
                ).fetchone()
            postgres_gate = {
                "status": "PASS",
                "migration": stage6_version["version"],
                "checkpoint_table": checkpoint_table["name"],
            }
        except Exception as exc:  # pragma: no cover - external service gate
            postgres_gate = {"status": "FAIL", "error": type(exc).__name__}
    else:
        postgres_gate = {
            "status": "SKIP",
            "reason": "CUA_REQUIRE_POSTGRES is not true",
        }

    static_pass = not missing and invalid_action_rejected
    postgres_pass = postgres_gate["status"] in {"PASS", "SKIP"}
    payload = {
        "stage": 6,
        "status": "PASS" if static_pass and postgres_pass else "FAIL",
        "static_contracts": {
            "status": "PASS" if static_pass else "FAIL",
            "missing_files": missing,
            "invalid_action_rejected": invalid_action_rejected,
        },
        "postgres": postgres_gate,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
