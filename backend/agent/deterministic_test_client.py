"""Local structured planner used only by the isolated Chromium test environment."""

from __future__ import annotations

import re
from typing import Any

from backend.agent.planner import ModelResponse


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

    @staticmethod
    def _task_id(observation: str) -> str:
        """Identify the isolated fixture from its current semantic controls."""
        if 'combobox "Warna"' in observation:
            return "T05"
        if 'radio "Pilih Selasa' in observation:
            return "T07"
        if 'textbox "Nama tampilan dummy"' in observation:
            return "T12"
        if 'checkbox "Item pilot A"' in observation:
            return "P02"
        if 'radio "Pilih daring pukul' in observation:
            return "P03"
        if 'combobox "Zona waktu draft"' in observation:
            return "P04"
        if 'radio "Pilih rute pilot pukul' in observation or 'radio "Gunakan rute pilot pukul' in observation:
            return "P01"
        return "T01"

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

        task_id = self._task_id(observation)

        if task_id == "T01" and not verified:
            target_ref, name, version = self._target(
                observation,
                "radio",
                ("Pilih rute 09:45", "Gunakan opsi 09:45", "Pilih rute 09:30", "Gunakan opsi 09:30"),
            )
            payload = {
                "action": {
                    "action_type": "check",
                    "target_ref": target_ref,
                    "observation_version": version,
                    "expected_effect": f"{name} dipilih dan terverifikasi.",
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
        elif task_id == "T01":
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
        elif task_id == "T05":
            steps = (
                ("select", "combobox", ("Warna",), "Navy", "Warna Navy dipilih.", "element_state", True),
                ("select", "combobox", ("Ukuran",), "M", "Ukuran M dipilih.", "element_state", True),
                ("select", "combobox", ("Jumlah", "Kuantitas"), "2", "Jumlah dua dipilih.", "element_state", True),
                ("click", "button", ("Tambahkan ke cart sintetis",), None, "Produk ditambahkan ke cart sintetis.", "text", "Variasi ditambahkan"),
            )
            payload = self._step_payload(observation, len(verified), steps)
        elif task_id == "T07":
            steps = (
                ("check", "radio", ("Pilih Selasa 13:30 dengan Rina", "Pilih Selasa 13:35 dengan Rina"), None, "Slot valid dengan Rina dipilih.", "element_state", True),
                ("click", "button", ("Simpan slot untuk review",), None, "Slot disimpan untuk review.", "text", "Slot dipilih untuk review"),
            )
            payload = self._step_payload(observation, len(verified), steps)
        elif task_id == "T12":
            steps = (
                ("type", "textbox", ("Nama tampilan dummy",), "Budi Demo", "Nama tampilan dummy diisi.", "field_value", "Budi Demo"),
                ("type", "textbox", ("Bio dummy",), "Pengguna uji aksesibilitas", "Bio dummy diisi.", "field_value", "Pengguna uji aksesibilitas"),
                ("click", "button", ("Simpan draft profil", "Simpan tanpa menerapkan"), None, "Profil dummy disimpan sebagai draft.", "text", "Profil dummy disimpan sebagai draft"),
            )
            payload = self._step_payload(observation, len(verified), steps)
        elif task_id == "P01":
            valid_times = tuple(
                f"{prefix} {hour}:{minute:02d}"
                for prefix in ("Pilih rute pilot pukul", "Gunakan rute pilot pukul")
                for hour, minute in ((10, 20), (10, 25), (10, 30), (10, 35), (10, 40))
            )
            steps = (
                ("check", "radio", valid_times, None, "Rute pilot setelah pukul sepuluh dipilih.", "element_state", True),
                ("click", "button", ("Simpan rute sebagai draft",), None, "Rute pilot disimpan sebagai draft.", "text", "Rute pilot disimpan sebagai draft"),
            )
            payload = self._step_payload(observation, len(verified), steps)
        elif task_id == "P02":
            steps = (
                ("check", "checkbox", ("Item pilot A",), None, "Item pilot A dipilih.", "element_state", True),
                ("check", "checkbox", ("Item pilot B",), None, "Item pilot B dipilih.", "element_state", True),
                ("click", "button", ("Simpan daftar perbandingan pilot",), None, "Dua item pilot disimpan untuk dibandingkan.", "text", "Daftar perbandingan pilot diperbarui"),
            )
            payload = self._step_payload(observation, len(verified), steps)
        elif task_id == "P03":
            valid_times = tuple(
                f"Pilih daring pukul 0{hour}:{minute:02d}"
                for hour, minute in ((8, 50), (8, 55), (9, 0), (9, 5), (9, 10))
            )
            steps = (
                ("check", "radio", valid_times, None, "Slot daring pilot dipilih.", "element_state", True),
                ("click", "button", ("Simpan slot pilot tanpa konfirmasi",), None, "Slot pilot disimpan tanpa konfirmasi.", "text", "Slot pilot dipilih"),
            )
            payload = self._step_payload(observation, len(verified), steps)
        elif task_id == "P04":
            steps = (
                ("select", "combobox", ("Zona waktu draft",), "Asia/Jakarta", "Zona waktu draft dipilih.", "element_state", True),
                ("click", "button", ("Simpan zona waktu sebagai draft",), None, "Zona waktu disimpan sebagai draft.", "text", "Zona waktu pilot disimpan sebagai draft"),
            )
            payload = self._step_payload(observation, len(verified), steps)
        else:
            raise RuntimeError(f"Deterministic study client tidak mendukung {task_id}.")

        return ModelResponse(
            payload=payload,
            input_tokens=32,
            output_tokens=24,
            model_id=self.model_id,
            provider=self.provider,
            latency_ms=0,
        )

    @classmethod
    def _step_payload(
        cls,
        observation: str,
        index: int,
        steps: tuple[tuple[str, str, tuple[str, ...], str | None, str, str, object], ...],
    ) -> dict[str, Any]:
        if index >= len(steps):
            raise RuntimeError("Semua langkah deterministic sudah digunakan.")
        action_type, role, names, input_value, effect, predicate_kind, expected = steps[index]
        target_ref, name, version = cls._target(observation, role, names)
        action: dict[str, Any] = {
            "action_type": action_type,
            "target_ref": target_ref,
            "observation_version": version,
            "expected_effect": effect,
            "risk_level": "LOW",
            "requires_approval": False,
        }
        if input_value is not None:
            action["input_value"] = input_value
        predicate: dict[str, Any] = {
            "kind": predicate_kind,
            "role": "status" if predicate_kind == "text" else role,
            "expected": expected,
        }
        if predicate_kind == "text":
            predicate["match"] = "contains"
        elif predicate_kind == "field_value":
            predicate.update({"name": name, "match": "contains"})
        elif predicate_kind == "element_state":
            if action_type == "select":
                predicate.update({"role": "option", "name": input_value, "state_key": "selected"})
            else:
                predicate.update({"name": name, "state_key": "checked"})
        return {
            "action": action,
            "postconditions": [predicate],
            "reason": "Jalankan langkah studi yang cocok berdasarkan nama aksesibel.",
            "goal_complete_after_verification": index == len(steps) - 1,
        }

    def close(self) -> None:
        """Match the network planner client lifecycle."""
