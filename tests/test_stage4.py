from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("CUA_ENV", "test")
os.environ.setdefault("CUA_APP_SECRET", "stage4-test-secret-not-for-production")
os.environ.setdefault("CUA_REQUIRE_POSTGRES", "false")

from fastapi.testclient import TestClient  # noqa: E402

from apps.api.a11y_api.app import create_app  # noqa: E402
from apps.api.a11y_api.config import ConfigurationError, Settings  # noqa: E402


class Stage4ConfigurationTests(unittest.TestCase):
    def test_missing_secret_has_clear_error(self):
        with (
            patch.dict(os.environ, {"CUA_ENV": "development"}, clear=True),
            self.assertRaisesRegex(ConfigurationError, "CUA_APP_SECRET belum diisi"),
        ):
            Settings.from_env()

    def test_example_secret_is_rejected_outside_test(self):
        values = {
            "CUA_ENV": "development",
            "CUA_APP_SECRET": "ganti-dengan-random-string-lokal-minimal-24-karakter",
        }
        with (
            patch.dict(os.environ, values, clear=True),
            self.assertRaisesRegex(ConfigurationError, "nilai contoh tidak boleh dipakai"),
        ):
            Settings.from_env()

    def test_personal_home_cannot_be_browser_profile(self):
        values = {
            "CUA_ENV": "test",
            "CUA_APP_SECRET": "test-only",
            "CUA_BROWSER_PROFILE_DIR": str(Path.home() / "Chrome"),
        }
        with (
            patch.dict(os.environ, values, clear=True),
            self.assertRaisesRegex(ConfigurationError, "profil/home pribadi"),
        ):
            Settings.from_env()

    def test_api_and_dependency_health_are_machine_readable(self):
        client = TestClient(create_app(Settings.from_env()))
        health = client.get("/health")
        ready = client.get("/health/ready")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["dependencies"]["benchmark_catalog"]["tasks"], 12)
        self.assertTrue(
            ready.json()["dependencies"]["browser_profile"]["isolated_from_personal_profile"]
        )


class Stage4RepositoryContractTests(unittest.TestCase):
    def test_monorepo_boundaries_exist(self):
        required = [
            "apps/extension",
            "apps/api",
            "packages/agent",
            "benchmark",
            "evaluation",
            "tests",
            "docs",
            "evidence",
        ]
        for relative in required:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_dir())

    def test_python_and_frontend_dependencies_are_exactly_pinned(self):
        python_lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
        python_dev_lock = (ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
        self.assertNotIn(">=", python_lock + python_dev_lock)
        self.assertIn("fastapi==", python_lock)
        root_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        extension_package = json.loads(
            (ROOT / "apps" / "extension" / "package.json").read_text(encoding="utf-8")
        )
        for dependencies in (
            root_package["devDependencies"],
            extension_package["devDependencies"],
        ):
            for name, version in dependencies.items():
                with self.subTest(package=name):
                    self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_extension_is_mv3_least_privilege_accessible_shell(self):
        extension = ROOT / "apps" / "extension"
        manifest = json.loads((extension / "public" / "manifest.json").read_text(encoding="utf-8"))
        html = (extension / "sidepanel.html").read_text(encoding="utf-8")
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(manifest["side_panel"]["default_path"], "sidepanel.html")
        self.assertNotIn("tabs", manifest["permissions"])
        self.assertIn('lang="id"', html)
        self.assertIn("Dengarkan saya", html)
        self.assertIn("Hasil yang sudah diperiksa", html)
        self.assertIn("Shared control", html)

    def test_runtime_and_secret_artifacts_are_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for pattern in (".env", ".venv/", "node_modules/", ".runtime/"):
            self.assertIn(pattern, ignored)


if __name__ == "__main__":
    unittest.main()
