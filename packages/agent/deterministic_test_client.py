"""Local structured planner used only by the isolated Chromium test environment."""

from __future__ import annotations

import re
from typing import Any

from packages.agent.planner import ModelResponse


class DeterministicT01Client:
    """Drive the public T01 happy path from semantic observations, without an API key."""

    provider = "deterministic-test"
    model_id = "deterministic-t01-v1"

    @staticmethod
    def _target(observation: str, role: str, names: tuple[str, ...]) -> tuple[str, str, int]:
        for name in names:
            pattern = rf'\[(v(?P<version>\d+):ax\d+)\] {re.escape(role)} "{re.escape(name)}"'
            match = re.search(pattern, observation)
            if match:
                return match.group(1), name, int(match.group("version"))
        expected = " atau ".join(names)
        raise RuntimeError(f"Kontrol semantik {role} ({expected}) tidak ditemukan.")

    def generate(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        request: dict[str, Any],
    ) -> ModelResponse:
        del prompt, schema
        observation = str(request["compact_observation"])
        verified = list(request.get("verified_progress", []))

        if not verified:
            target_ref, name, version = self._target(
                observation,
                "radio",
                ("Pilih rute 09:45", "Gunakan opsi 09:45"),
            )
            payload = {
                "action": {
                    "action_type": "check",
                    "target_ref": target_ref,
                    "observation_version": version,
                    "expected_effect": "Rute 09:45 dipilih dan terverifikasi.",
                    "risk_level": "LOW",
                    "requires_approval": False,
                },
                "postconditions": [
                    {
                        "kind": "element_state",
                        "role": "radio",
                        "name": name,
                        "state_key": "checked",
                        "expected": True,
                    }
                ],
                "reason": "Pilih satu-satunya rute yang memenuhi batas waktu dan harga.",
                "goal_complete_after_verification": False,
            }
        else:
            target_ref, _, version = self._target(
                observation,
                "button",
                ("Simpan pilihan dan buka review",),
            )
            payload = {
                "action": {
                    "action_type": "click",
                    "target_ref": target_ref,
                    "observation_version": version,
                    "expected_effect": "Pilihan disimpan pada review tanpa melakukan booking.",
                    "risk_level": "LOW",
                    "requires_approval": False,
                },
                "postconditions": [
                    {
                        "kind": "text",
                        "role": "status",
                        "expected": "Rute dipilih",
                        "match": "contains",
                    }
                ],
                "reason": "Simpan pilihan lalu berhenti tepat pada batas aman review.",
                "goal_complete_after_verification": True,
            }

        return ModelResponse(
            payload=payload,
            input_tokens=32,
            output_tokens=24,
            model_id=self.model_id,
            provider=self.provider,
            latency_ms=0,
        )

    def close(self) -> None:
        """Match the network planner client lifecycle."""
