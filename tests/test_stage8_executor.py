from __future__ import annotations

import inspect
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from pydantic import ValidationError

from backend.agent.contracts import AgentAction, ErrorCode
from backend.agent.executor import (
    DeterministicExecutor,
    PrimitiveAction,
    PrimitiveActionRequest,
    map_playwright_exception,
)
from backend.agent.observer import AccessibilityObserver
from backend.agent.resolver import SemanticTargetResolver

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8015"
COMPONENTS = """
<main>
  <h1>Primitive components</h1>
  <label>Nama dummy <input value="Awal"></label>
  <label>Pilihan
    <select><option>Satu</option><option>Dua</option></select>
  </label>
  <label><input type="checkbox"> Setuju</label>
  <label><input type="checkbox" checked> Aktif</label>
  <button onclick="document.querySelector('[role=status]').textContent='Aktif';">Lanjut</button>
  <div style="height: 1600px"></div>
  <button>Target bawah</button>
  <p role="status">Siap</p>
</main>
"""


@pytest.fixture(scope="module")
def test_server() -> Iterator[None]:
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "run_test_server.py")],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{BASE_URL}/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        else:
            raise RuntimeError("Stage 8 test server did not become ready")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    if not page.is_closed():
        page.close()


def executor_stack(page, html: str = COMPONENTS):
    page.set_content(html)
    observer = AccessibilityObserver()
    observation = observer.capture(page)
    resolver = SemanticTargetResolver(observer.registry)
    return observer, observation, DeterministicExecutor(resolver)


def semantic_ref(observation, role: str, name: str) -> str:
    return next(node.node_id for node in observation.nodes if node.role == role and node.name == name)


@pytest.mark.parametrize(
    ("primitive", "role", "name", "value", "key"),
    [
        (PrimitiveAction.FOCUS, "textbox", "Nama dummy", None, None),
        (PrimitiveAction.FILL, "textbox", "Nama dummy", "Budi", None),
        (PrimitiveAction.ACTIVATE, "button", "Lanjut", None, None),
        (PrimitiveAction.SELECT, "combobox", "Pilihan", "Dua", None),
        (PrimitiveAction.CHECK, "checkbox", "Setuju", None, None),
        (PrimitiveAction.UNCHECK, "checkbox", "Aktif", None, None),
        (PrimitiveAction.PRESS, "textbox", "Nama dummy", None, "End"),
        (PrimitiveAction.SCROLL, "button", "Target bawah", None, None),
    ],
)
def test_target_primitive_happy_paths(page, primitive, role, name, value, key) -> None:
    _, observation, executor = executor_stack(page)
    request = PrimitiveActionRequest(
        primitive=primitive,
        target_ref=semantic_ref(observation, role, name),
        value=value,
        key=key,
        observation_version=observation.version,
    )

    result = executor.execute_primitive(page, request)

    assert result.success, result.model_dump_json()
    assert result.error_code is ErrorCode.NONE
    assert result.locator_summary is not None
    assert result.started_at <= result.ended_at
    if primitive is PrimitiveAction.FOCUS:
        assert page.get_by_role(role, name=name).evaluate("element => element === document.activeElement")
    elif primitive is PrimitiveAction.FILL:
        assert page.get_by_role(role, name=name).input_value() == value
    elif primitive is PrimitiveAction.ACTIVATE:
        assert page.get_by_role("status").text_content() == "Aktif"
    elif primitive is PrimitiveAction.SELECT:
        assert page.get_by_role(role, name=name).input_value() == "Dua"
    elif primitive is PrimitiveAction.CHECK:
        assert page.get_by_role(role, name=name).is_checked()
    elif primitive is PrimitiveAction.UNCHECK:
        assert not page.get_by_role(role, name=name).is_checked()


@pytest.mark.parametrize(
    ("primitive", "element", "role", "name", "value", "key"),
    [
        (PrimitiveAction.FOCUS, '<input aria-label="Target" disabled>', "textbox", "Target", None, None),
        (PrimitiveAction.FILL, '<input aria-label="Target" disabled>', "textbox", "Target", "x", None),
        (PrimitiveAction.ACTIVATE, "<button disabled>Target</button>", "button", "Target", None, None),
        (
            PrimitiveAction.SELECT,
            '<select aria-label="Target" disabled><option>A</option></select>',
            "combobox",
            "Target",
            "A",
            None,
        ),
        (
            PrimitiveAction.CHECK,
            '<input type="checkbox" aria-label="Target" disabled>',
            "checkbox",
            "Target",
            None,
            None,
        ),
        (
            PrimitiveAction.UNCHECK,
            '<input type="checkbox" aria-label="Target" checked disabled>',
            "checkbox",
            "Target",
            None,
            None,
        ),
        (PrimitiveAction.PRESS, '<input aria-label="Target" disabled>', "textbox", "Target", None, "End"),
        (PrimitiveAction.SCROLL, "<button disabled>Target</button>", "button", "Target", None, None),
    ],
)
def test_every_target_primitive_rejects_disabled(page, primitive, element, role, name, value, key) -> None:
    _, observation, executor = executor_stack(page, f"<main>{element}</main>")
    request = PrimitiveActionRequest(
        primitive=primitive,
        target_ref=semantic_ref(observation, role, name),
        value=value,
        key=key,
        observation_version=observation.version,
    )

    result = executor.execute_primitive(page, request)

    assert not result.success
    assert result.error_code is ErrorCode.TARGET_DISABLED


@pytest.mark.parametrize(
    ("primitive", "elements", "role", "name", "value", "key"),
    [
        (
            PrimitiveAction.FOCUS,
            '<input aria-label="Target"><input aria-label="Target">',
            "textbox",
            "Target",
            None,
            None,
        ),
        (
            PrimitiveAction.FILL,
            '<input aria-label="Target"><input aria-label="Target">',
            "textbox",
            "Target",
            "x",
            None,
        ),
        (
            PrimitiveAction.ACTIVATE,
            "<button>Target</button><button>Target</button>",
            "button",
            "Target",
            None,
            None,
        ),
        (
            PrimitiveAction.SELECT,
            '<select aria-label="Target"><option>A</option></select><select aria-label="Target"><option>A</option></select>',
            "combobox",
            "Target",
            "A",
            None,
        ),
        (
            PrimitiveAction.CHECK,
            '<input type="checkbox" aria-label="Target"><input type="checkbox" aria-label="Target">',
            "checkbox",
            "Target",
            None,
            None,
        ),
        (
            PrimitiveAction.UNCHECK,
            '<input type="checkbox" aria-label="Target" checked><input type="checkbox" aria-label="Target" checked>',
            "checkbox",
            "Target",
            None,
            None,
        ),
        (
            PrimitiveAction.PRESS,
            '<input aria-label="Target"><input aria-label="Target">',
            "textbox",
            "Target",
            None,
            "End",
        ),
        (
            PrimitiveAction.SCROLL,
            "<button>Target</button><button>Target</button>",
            "button",
            "Target",
            None,
            None,
        ),
    ],
)
def test_every_target_primitive_rejects_ambiguity(page, primitive, elements, role, name, value, key) -> None:
    _, observation, executor = executor_stack(page, f"<main>{elements}</main>")
    request = PrimitiveActionRequest(
        primitive=primitive,
        target_ref=semantic_ref(observation, role, name),
        value=value,
        key=key,
        observation_version=observation.version,
    )

    result = executor.execute_primitive(page, request)

    assert not result.success
    assert result.error_code is ErrorCode.AMBIGUOUS_TARGET


def test_detached_or_rerendered_target_requires_new_observation(page) -> None:
    _, observation, executor = executor_stack(page, "<main><button>Lanjut</button></main>")
    request = PrimitiveActionRequest(
        primitive=PrimitiveAction.ACTIVATE,
        target_ref=semantic_ref(observation, "button", "Lanjut"),
        observation_version=observation.version,
    )
    page.set_content("<main><button>Lanjut baru</button></main>")

    result = executor.execute_primitive(page, request)

    assert result.error_code is ErrorCode.STALE_OBSERVATION
    assert result.needs_reobserve is True


def test_press_policy_blocks_unapproved_key(page) -> None:
    _, observation, executor = executor_stack(page)
    result = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.PRESS,
            target_ref=semantic_ref(observation, "textbox", "Nama dummy"),
            key="Control+L",
            observation_version=observation.version,
        ),
    )
    assert result.error_code is ErrorCode.POLICY_BLOCKED


def test_sensitive_and_high_risk_targets_cannot_bypass_policy(page) -> None:
    _, observation, executor = executor_stack(page, "<main><button>Bayar sekarang</button></main>")
    target_ref = semantic_ref(observation, "button", "Bayar sekarang")
    blocked = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.ACTIVATE,
            target_ref=target_ref,
            observation_version=observation.version,
        ),
        approval_granted=True,
    )
    assert blocked.error_code is ErrorCode.POLICY_BLOCKED

    _, observation, executor = executor_stack(page, "<main><button>Kirim</button></main>")
    approval = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.ACTIVATE,
            target_ref=semantic_ref(observation, "button", "Kirim"),
            observation_version=observation.version,
            risk_level="HIGH",
            requires_approval=True,
        ),
    )
    assert approval.error_code is ErrorCode.APPROVAL_REQUIRED


def test_navigation_happy_path_and_two_policy_failures(page, test_server) -> None:
    page.goto(BASE_URL)
    observer = AccessibilityObserver()
    observation = observer.capture(page)
    executor = DeterministicExecutor(SemanticTargetResolver(observer.registry))
    success = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.NAVIGATE,
            value="/travel",
            observation_version=observation.version,
        ),
    )
    assert success.success
    assert page.url == f"{BASE_URL}/travel"

    observation = observer.capture(page)
    external = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.NAVIGATE,
            value="https://example.com",
            observation_version=observation.version,
        ),
    )
    assert external.error_code is ErrorCode.POLICY_BLOCKED

    with pytest.raises(ValidationError):
        PrimitiveActionRequest(
            primitive=PrimitiveAction.NAVIGATE,
            observation_version=observation.version,
        )


def test_back_happy_path_no_history_and_navigation_interruption(page, browser, test_server) -> None:
    page.goto(BASE_URL)
    page.goto(f"{BASE_URL}/travel")
    observer = AccessibilityObserver()
    observation = observer.capture(page)
    executor = DeterministicExecutor(SemanticTargetResolver(observer.registry))
    result = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.BACK,
            observation_version=observation.version,
        ),
    )
    assert result.success
    assert page.url == f"{BASE_URL}/"

    isolated = browser.new_page()
    isolated.set_content("<main><h1>Tanpa history</h1></main>")
    isolated_observer = AccessibilityObserver()
    isolated_observation = isolated_observer.capture(isolated)
    isolated_executor = DeterministicExecutor(SemanticTargetResolver(isolated_observer.registry))
    no_history = isolated_executor.execute_primitive(
        isolated,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.BACK,
            observation_version=isolated_observation.version,
        ),
    )
    assert no_history.error_code is ErrorCode.INVALID_ACTION
    isolated.close()

    closed = browser.new_page()
    closed.set_content("<main><h1>Close</h1></main>")
    closed_observer = AccessibilityObserver()
    closed_observation = closed_observer.capture(closed)
    closed_executor = DeterministicExecutor(SemanticTargetResolver(closed_observer.registry))
    closed.close()
    interruption = closed_executor.execute_primitive(
        closed,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.BACK,
            observation_version=closed_observation.version,
        ),
    )
    assert interruption.error_code is ErrorCode.NAVIGATION_INTERRUPTED


def test_wait_happy_path_invalid_duration_and_bounded_policy(page) -> None:
    _, observation, executor = executor_stack(page)
    success = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.WAIT,
            value="1",
            observation_version=observation.version,
        ),
    )
    assert success.success

    invalid = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.WAIT,
            value="later",
            observation_version=observation.version,
        ),
    )
    assert invalid.error_code is ErrorCode.INVALID_ACTION

    excessive = executor.execute_primitive(
        page,
        PrimitiveActionRequest(
            primitive=PrimitiveAction.WAIT,
            value="9999",
            observation_version=observation.version,
        ),
    )
    assert excessive.error_code is ErrorCode.POLICY_BLOCKED


def test_exception_taxonomy_and_action_log_are_stable(page) -> None:
    assert map_playwright_exception(PlaywrightTimeoutError("timeout")) is ErrorCode.ACTION_TIMEOUT
    assert map_playwright_exception(RuntimeError("element was detached")) is ErrorCode.STALE_OBSERVATION
    assert (
        map_playwright_exception(RuntimeError("Target page has been closed"))
        is ErrorCode.NAVIGATION_INTERRUPTED
    )

    _, observation, executor = executor_stack(page)
    secret = "secret-value-must-not-enter-log"
    result = executor.execute(
        page,
        AgentAction(
            action_type="type",
            target_ref=semantic_ref(observation, "textbox", "Nama dummy"),
            input_value=secret,
            observation_version=observation.version,
            expected_effect="Field terisi",
        ),
    )
    assert result.success
    assert secret not in result.model_dump_json()
    source = inspect.getsource(DeterministicExecutor)
    assert "click(" not in source
    assert "mouse." not in source
