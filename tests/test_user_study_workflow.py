from __future__ import annotations

import os
import unittest

os.environ.setdefault("CUA_ENV", "test")
os.environ.setdefault("CUA_APP_SECRET", "study-workflow-test-secret")
os.environ.setdefault("CUA_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CUA_PLANNER_PROVIDER", "deterministic")

from fastapi.testclient import TestClient  # noqa: E402

from apps.api.a11y_api.app import create_app  # noqa: E402
from apps.api.a11y_api.config import Settings  # noqa: E402


class HandsFreeStudyWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app(Settings.from_env()))

    def create_session(self, **overrides: object) -> dict:
        payload = {
            "participant_code": "P01",
            "condition_id": "C0",
            "is_minor": False,
            "guardian_consent_confirmed": False,
            **overrides,
        }
        response = self.client.post("/api/study/sessions", json=payload)
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_consent_checks_and_cold_start_are_enforced(self) -> None:
        session = self.create_session()
        study_id = session["study_session_id"]

        for key in ("store_name", "photo", "webcam_audio", "screen"):
            response = self.client.post(
                f"/api/study/sessions/{study_id}/consent",
                json={"key": key, "granted": key == "store_name"},
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "CHECKS")
        self.assertEqual(
            self.client.post(f"/api/study/sessions/{study_id}/tasks/start").status_code,
            409,
        )

        for key in ("audio", "screen_reader"):
            response = self.client.post(
                f"/api/study/sessions/{study_id}/checks",
                json={"key": key, "passed": True},
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "READY")

        started = self.client.post(f"/api/study/sessions/{study_id}/tasks/start")
        self.assertEqual(started.status_code, 200)
        payload = started.json()
        self.assertEqual(payload["status"], "TASK_ACTIVE")
        self.assertIn(f"study_session_id={study_id}", payload["start_url"])
        task_page = self.client.get(payload["start_url"])
        self.assertEqual(task_page.status_code, 200)
        self.assertNotIn("Cari rute Medan", task_page.text)
        self.assertNotIn("Tujuan tugas", task_page.text)
        self.assertNotIn("Kontrol eksperimen", task_page.text)
        self.assertNotIn("Task T01", task_page.text)

        completed = self.client.post(
            f"/api/study/sessions/{study_id}/tasks/complete",
            json={"outcome": "RESEARCHER_CONFIRMED"},
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["status"], "BETWEEN_TASKS")
        self.assertEqual(completed.json()["current_task"]["task_id"], "T05")

    def test_minor_requires_guardian_consent_before_session_creation(self) -> None:
        response = self.client.post(
            "/api/study/sessions",
            json={
                "participant_code": "P02",
                "condition_id": "C0",
                "is_minor": True,
                "guardian_consent_confirmed": False,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("orang tua atau wali", response.json()["detail"])

    def test_researcher_console_is_available_without_participant_controls(self) -> None:
        response = self.client.get("/researcher")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Khusus peneliti", response.text)
        self.assertIn("Tidak ada latihan", response.text)


if __name__ == "__main__":
    unittest.main()
