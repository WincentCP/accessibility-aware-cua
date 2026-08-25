from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from packages.agent.observer import AccessibilityObserver, SemanticResolutionError
from packages.agent.semantic_snapshot import (
    ObserverErrorCode,
    ResolutionStatus,
    TargetQuery,
)


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


def test_observer_detects_dialog_status_error_and_focus_change(page) -> None:
    page.set_content(
        """
        <main>
          <h1>Ubah profil</h1>
          <label for="name">Nama dummy</label>
          <input id="name" aria-invalid="true" aria-describedby="name-error">
          <p id="name-error" role="alert">Nama wajib diisi.</p>
          <p role="status">Draft belum disimpan.</p>
          <div role="dialog" aria-label="Konfirmasi perubahan">
            <button>Simpan draft</button>
          </div>
        </main>
        """
    )
    page.get_by_role("textbox", name="Nama dummy").focus()
    observer = AccessibilityObserver()
    observation = observer.capture(page)

    assert observation.focused_node_id is not None
    assert {"dialog", "status", "alert", "textbox"} <= {
        node.role for node in observation.nodes
    }
    assert observer.registry.query(
        TargetQuery(
            role="dialog",
            name="Konfirmasi perubahan",
            observation_version=observation.version,
        )
    ).status is ResolutionStatus.FOUND
    assert observer.registry.query(
        TargetQuery(
            role="status",
            name="Draft belum disimpan.",
            observation_version=observation.version,
        )
    ).status is ResolutionStatus.FOUND


def test_browser_rerender_invalidates_old_ref_and_marks_duplicate_name(page) -> None:
    page.set_content('<main><button id="only">Lanjut</button></main>')
    observer = AccessibilityObserver()
    first = observer.capture(page)
    old_ref = observer.registry.query(
        TargetQuery(role="button", name="Lanjut", observation_version=first.version)
    ).semantic_ref
    assert old_ref is not None

    page.set_content('<main><button>Lanjut</button><button>Lanjut</button></main>')
    second = observer.capture(page)
    assert observer.registry.resolve_ref(old_ref).error_code is ObserverErrorCode.STALE_OBSERVATION
    ambiguous = observer.registry.query(
        TargetQuery(role="button", name="Lanjut", observation_version=second.version)
    )
    assert ambiguous.error_code is ObserverErrorCode.AMBIGUOUS_TARGET

    with pytest.raises(SemanticResolutionError) as error:
        observer.locator_for(
            page,
            TargetQuery(role="button", name="Lanjut", observation_version=second.version),
        )
    assert error.value.code is ObserverErrorCode.AMBIGUOUS_TARGET


def test_extension_namespace_is_removed_only_from_agent_snapshot(page) -> None:
    page.set_content(
        """
        <main>
          <h1>Task pengguna</h1>
          <button>Kerjakan</button>
          <aside aria-label="Accessibility-Aware CUA extension panel">
            <button>Kontrol internal extension</button>
          </aside>
        </main>
        """
    )
    observer = AccessibilityObserver()
    observation = observer.capture(page)

    assert page.get_by_role("button", name="Kontrol internal extension").count() == 1
    assert all("extension" not in node.name.casefold() for node in observation.nodes)
    assert all(node.name != "Kontrol internal extension" for node in observation.nodes)
