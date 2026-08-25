from __future__ import annotations

import os
import time
import unittest
from html import unescape
from html.parser import HTMLParser

os.environ.setdefault("CUA_ENV", "test")
os.environ.setdefault("CUA_APP_SECRET", "stage5-test-secret-not-for-production")
os.environ.setdefault("CUA_REQUIRE_POSTGRES", "false")

from fastapi.testclient import TestClient  # noqa: E402

from a11y_benchmark.catalog import CONDITIONS, FINAL_TASKS  # noqa: E402
from a11y_benchmark.manifests import final_seed  # noqa: E402
from a11y_benchmark.oracles.engine import evaluate  # noqa: E402
from apps.api.a11y_api.app import app  # noqa: E402

FORBIDDEN_PUBLIC_KEYS = {
    "initial_state",
    "success_patch",
    "predicates",
    "invariants",
    "near_misses",
    "expected_final_state",
    "target_id",
    "oracle",
    "handoff_oracle",
    "focus_target",
}


def all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from all_keys(nested)


class SemanticAuditParser(HTMLParser):
    """Small deterministic structural audit; the browser suite runs axe separately."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.title_depth = 0
        self.title_text = ""
        self.main_count = 0
        self.h1_count = 0
        self.ids: list[str] = []
        self.label_for: set[str] = set()
        self.unlabelled_controls: list[str] = []
        self.label_depth = 0
        self.external_urls: list[str] = []
        self.positive_tabindex: list[str] = []
        self.live_regions = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "html":
            self.lang = attributes.get("lang", "")
        if tag == "title":
            self.title_depth += 1
        if tag == "main":
            self.main_count += 1
        if tag == "h1":
            self.h1_count += 1
        if tag == "label":
            self.label_depth += 1
            if attributes.get("for"):
                self.label_for.add(attributes["for"])
        if attributes.get("id"):
            self.ids.append(attributes["id"])
        if attributes.get("aria-live"):
            self.live_regions += 1
        tabindex = attributes.get("tabindex")
        if tabindex and tabindex.lstrip("+").isdigit() and int(tabindex) > 0:
            self.positive_tabindex.append(f"{tag}[tabindex={tabindex}]")
        if tag in {"a", "script", "link", "img"}:
            url = attributes.get("href") or attributes.get("src") or ""
            if url.startswith(("http://", "https://", "//")):
                self.external_urls.append(url)
        if tag in {"input", "select", "textarea"}:
            control_type = attributes.get("type", "text")
            labelled = (
                self.label_depth > 0
                or bool(attributes.get("aria-label"))
                or bool(attributes.get("aria-labelledby"))
                or (bool(attributes.get("id")) and attributes["id"] in self.label_for)
            )
            if control_type != "hidden" and not labelled:
                self.unlabelled_controls.append(attributes.get("name", tag))

    def handle_endtag(self, tag):
        if tag == "title":
            self.title_depth -= 1
        if tag == "label":
            self.label_depth -= 1

    def handle_data(self, data):
        if self.title_depth:
            self.title_text += data

    def assert_accessible_structure(self, test_case: unittest.TestCase):
        test_case.assertEqual(self.lang, "id")
        test_case.assertTrue(self.title_text.strip())
        test_case.assertEqual(self.main_count, 1)
        test_case.assertEqual(self.h1_count, 1)
        test_case.assertEqual(len(self.ids), len(set(self.ids)), "Duplicate HTML id")
        test_case.assertEqual(self.unlabelled_controls, [])
        test_case.assertEqual(self.external_urls, [])
        test_case.assertEqual(self.positive_tabindex, [])
        test_case.assertGreaterEqual(self.live_regions, 1)


SUCCESS_FORMS = {
    "T01": {"route_id": "tr01"},
    "T02": {"direct_only": "on", "route_id": "tr11"},
    "T03": {"name": "Budi Santoso", "document_id": "TEST-0003", "accepted_schedule": "15:30"},
    "T04": {"product_id": "mp01"},
    "T05": {"color": "Navy", "size": "M", "quantity": "2"},
    "T06": {"address": "Jl. Contoh No. 12", "city": "Medan", "postal_code": "20000"},
    "T07": {"slot_id": "ap01"},
    "T08": {"name": "Dita Demo", "topic": "Orientasi layanan", "date": "2026-10-22", "time": "10:00"},
    "T09": {"date": "2026-10-24", "time": "14:00"},
    "T10": {"push": "on", "weekly": "on"},
    "T11": {"locale": "id-ID", "theme": "dark"},
    "T12": {"display_name": "Budi Demo", "bio": "Pengguna uji aksesibilitas"},
}


class Stage5MiniSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.store = app.state.case_store

    def reset(self, task_id: str, condition_id: str, seed: int):
        response = self.client.post(
            "/api/benchmark/reset",
            json={"task_id": task_id, "condition_id": condition_id, "seed": seed},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_all_36_cases_open_and_pass_structural_accessibility_audit(self):
        opened = 0
        for task in FINAL_TASKS:
            for condition_id in CONDITIONS:
                seed = final_seed(task["id"], condition_id, 1)
                reset = self.reset(task["id"], condition_id, seed)
                response = self.client.get(reset["start_url"])
                with self.subTest(task=task["id"], condition=condition_id):
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(task["goal"], unescape(response.text))
                    self.assertNotIn("data-testid", response.text)
                    parser = SemanticAuditParser()
                    parser.feed(response.text)
                    parser.assert_accessible_structure(self)
                opened += 1
        self.assertEqual(opened, 36)

    def test_correct_keyboard_form_path_passes_hidden_oracle_for_36_cases(self):
        passed = 0
        for task in FINAL_TASKS:
            for condition_id in CONDITIONS:
                seed = final_seed(task["id"], condition_id, 1)
                reset = self.reset(task["id"], condition_id, seed)
                response = self.client.post(
                    f"/api/benchmark/sessions/{reset['session_id']}/actions",
                    data=SUCCESS_FORMS[task["id"]],
                    follow_redirects=True,
                )
                state = self.store.private_state(reset["session_id"])
                result = evaluate(task["id"], state)
                with self.subTest(task=task["id"], condition=condition_id):
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertTrue(result["pass"], result)
                passed += 1
        self.assertEqual(passed, 36)

    def test_reset_is_idempotent_and_clears_stale_state_100_times(self):
        cases = [("T01", "C0"), ("T05", "C1"), ("T08", "C2"), ("T11", "C2")]
        for index in range(100):
            task_id, condition_id = cases[index % len(cases)]
            seed = 500_000 + index
            first = self.reset(task_id, condition_id, seed)
            initial = self.store.private_state(first["session_id"])
            self.store.apply_action(first["session_id"], SUCCESS_FORMS[task_id])
            mutated = self.store.private_state(first["session_id"])
            second = self.reset(task_id, condition_id, seed)
            restored = self.store.private_state(second["session_id"])
            third = self.reset(task_id, condition_id, seed)
            with self.subTest(iteration=index, task=task_id, condition=condition_id):
                self.assertNotEqual(mutated, initial)
                self.assertEqual(second, third)
                self.assertEqual(restored, initial)

    def test_public_http_surface_does_not_expose_oracle_truth(self):
        reset = self.reset("T08", "C2", 812_345)
        public_session = self.client.get(
            f"/api/benchmark/sessions/{reset['session_id']}"
        ).json()
        page = self.client.get(reset["start_url"]).text.lower()
        self.assertEqual(set(all_keys(reset)) & FORBIDDEN_PUBLIC_KEYS, set())
        self.assertEqual(set(all_keys(public_session)) & FORBIDDEN_PUBLIC_KEYS, set())
        self.assertNotIn("success_patch", page)
        self.assertNotIn("near_misses", page)
        self.assertNotIn("expected_final_state", page)
        paths = set(self.client.get("/openapi.json").json()["paths"])
        self.assertFalse(any("oracle" in path or "private" in path for path in paths))

    def test_c1_reorders_presentation_without_changing_ground_truth(self):
        seed = 700_001
        c0 = self.reset("T04", "C0", seed)
        c1 = self.reset("T04", "C1", seed)
        view0 = self.client.get(f"/api/benchmark/sessions/{c0['session_id']}").json()
        view1 = self.client.get(f"/api/benchmark/sessions/{c1['session_id']}").json()
        html1 = self.client.get(c1["start_url"]).text
        self.assertEqual({item["id"] for item in view0["records"]}, {item["id"] for item in view1["records"]})
        self.assertEqual(view1["presentation"]["layout_variant"], "reflowed")
        self.assertIn("reflowed", html1)
        self.assertIn("Simpan", html1)

    def test_c2_applies_declared_deterministic_delay_and_rerender(self):
        reset = self.reset("T01", "C2", 810_777)
        view = self.client.get(f"/api/benchmark/sessions/{reset['session_id']}").json()
        declared_ms = view["presentation"]["delay_ms"]
        started = time.perf_counter()
        response = self.client.post(
            f"/api/benchmark/sessions/{reset['session_id']}/actions",
            data=SUCCESS_FORMS["T01"],
            follow_redirects=True,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertEqual(response.status_code, 200)
        self.assertTrue(view["presentation"]["rerender_once"])
        self.assertGreaterEqual(elapsed_ms, declared_ms - 25)
        self.assertIn("Mode dinamis aktif", response.text)

    def test_no_unsafe_commit_controls_exist(self):
        forbidden_button_words = (">booking<", ">checkout<", ">bayar<", ">hapus akun<", ">konfirmasi janji<")
        for task in FINAL_TASKS:
            reset = self.reset(task["id"], "C0", final_seed(task["id"], "C0", 1))
            html = self.client.get(reset["start_url"]).text.lower().replace("\n", " ")
            for word in forbidden_button_words:
                with self.subTest(task=task["id"], word=word):
                    self.assertNotIn(word, html)

    def test_invalid_form_action_returns_accessible_error_without_mutation(self):
        reset = self.reset("T01", "C0", 912_001)
        before = self.store.private_state(reset["session_id"])
        response = self.client.post(
            f"/api/benchmark/sessions/{reset['session_id']}/actions",
            data={"route_id": "not-in-fixture"},
        )
        after = self.store.private_state(reset["session_id"])
        self.assertEqual(response.status_code, 422)
        self.assertIn("Input belum disimpan", response.text)
        parser = SemanticAuditParser()
        parser.feed(response.text)
        parser.assert_accessible_structure(self)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
