from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("CUA_ENV", "test")
os.environ.setdefault("CUA_APP_SECRET", "study-workflow-test-secret")
os.environ.setdefault("CUA_REQUIRE_POSTGRES", "false")
os.environ.setdefault("CUA_PLANNER_PROVIDER", "deterministic")

from fastapi.testclient import TestClient  # noqa: E402

from apps.api.a11y_api.app import STUDY_RESULTS_DIR, create_app  # noqa: E402
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
        self.assertIn("Sesi Kegiatan", response.text)
        self.assertIn("cukup dengarkan dan bicara", response.text)
        self.assertIn("Mulai Penelitian", response.text)
        self.assertIn("tidak perlu menekan tombol aplikasi lagi", response.text)
        self.assertNotIn("Kode peserta", response.text)
        self.assertNotIn("consent", response.text.lower())
        self.assertNotIn("Periksa sistem", response.text)

    def test_automatic_session_collects_profile_and_runs_four_tasks(self) -> None:
        created = self.client.post("/api/study/automatic", json={"condition_id": "C0"})
        self.assertEqual(created.status_code, 201)
        session = created.json()
        study_id = session["study_session_id"]
        self.assertTrue(session["automatic_mode"])
        self.assertTrue(session["participant_code"].startswith("anon-"))
        self.assertEqual(session["status"], "INITIALIZING")

        readiness = self.client.post(
            f"/api/study/sessions/{study_id}/automatic-readiness",
            json={
                "checks": {
                    "backend": True,
                    "agent": True,
                    "microphone": True,
                    "camera": True,
                    "screen": True,
                    "audio": True,
                }
            },
        )
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.json()["status"], "PROFILE")

        profile = self.client.post(
            f"/api/study/sessions/{study_id}/participant-profile",
            json={
                "name": "Raka",
                "name_spelling": "R A K A",
                "participant_class": "Kelas 8",
                "age": 14,
            },
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["status"], "READY")
        self.assertEqual(profile.json()["participant_name"], "Raka")
        self.assertEqual(profile.json()["participant_class"], "Kelas 8")
        self.assertEqual(profile.json()["participant_age"], 14)
        self.assertTrue(profile.json()["is_minor"])

        for index, task_id in enumerate(("T01", "T05", "T07", "T12")):
            started = self.client.post(f"/api/study/sessions/{study_id}/tasks/start")
            self.assertEqual(started.status_code, 200)
            self.assertEqual(started.json()["current_task"]["task_id"], task_id)
            utterance = self.client.post(
                f"/api/study/sessions/{study_id}/utterances",
                json={"text": "iya" if index == 0 else "lanjut"},
            )
            self.assertEqual(utterance.status_code, 200)
            self.assertEqual(utterance.json()["utterance_id"], index + 1)
            completed = self.client.post(
                f"/api/study/sessions/{study_id}/tasks/complete",
                json={"outcome": "AGENT_VERIFIED"},
            )
            self.assertEqual(completed.status_code, 200)

        final = completed.json()
        self.assertEqual(final["status"], "FEEDBACK")
        feedback = self.client.post(
            f"/api/study/sessions/{study_id}/feedback",
            json={"text": "Mudah digunakan, tetapi pilihan suara bisa dibuat lebih singkat."},
        )
        self.assertEqual(feedback.status_code, 200)
        self.assertEqual(feedback.json()["status"], "CLOSING")
        finished = self.client.post(f"/api/study/sessions/{study_id}/complete")
        self.assertEqual(finished.status_code, 200)
        final = finished.json()
        self.assertEqual(final["status"], "COMPLETED")
        self.assertEqual(final["voice_state"], "COMPLETE")
        self.assertIn("Mudah digunakan", final["feedback"]["text"])
        self.assertIsNone(final["current_task"])
        recording_saved = self.client.post(
            f"/api/study/sessions/{study_id}/recording-state",
            json={"state": "SAVED"},
        )
        self.assertEqual(recording_saved.status_code, 200)
        exported = self.client.get(f"/api/study/sessions/{study_id}/result")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.json()["format_version"], "1.0")
        self.assertEqual(exported.json()["recording_state"], "SAVED")
        self.assertEqual(
            exported.json()["recordings"]["screen_with_camera"], "screen.webm"
        )
        persisted = json.loads(
            (STUDY_RESULTS_DIR / f"{study_id}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(persisted["recording_state"], "SAVED")
        report = self.client.get(f"/api/study/sessions/{study_id}/report.pdf")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.headers["content-type"], "application/pdf")
        self.assertTrue(report.content.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
