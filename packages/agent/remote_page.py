"""Minimal loopback Playwright page proxy used by the live FastAPI agent."""

from __future__ import annotations

from typing import Any

import httpx


class RemoteBridgeError(RuntimeError):
    pass


class RemoteLocator:
    def __init__(
        self,
        page: RemotePage,
        *,
        selector: str | None = None,
        role: str | None = None,
        name: str | None = None,
        exact: bool = True,
    ) -> None:
        self.page = page
        self.selector = selector
        self.role = role
        self.name = name
        self.exact = exact

    def _target(self) -> dict[str, Any]:
        return {"role": self.role, "name": self.name, "exact": self.exact}

    def _inspect(self) -> dict[str, Any]:
        if self.role is None:
            return {"count": self.count()}
        return self.page._post("/page/locator", self._target())

    def count(self) -> int:
        if self.selector is not None:
            return int(self.page._post("/page/aria", {"selector": self.selector})["count"])
        return int(self._inspect()["count"])

    def aria_snapshot(self, *, timeout: int = 5_000) -> str:
        del timeout
        payload = self.page._post("/page/aria", {"selector": self.selector or "body"})
        if payload["count"] != 1 or payload["snapshot"] is None:
            raise RemoteBridgeError("ARIA snapshot target harus unik.")
        return str(payload["snapshot"])

    def is_visible(self) -> bool:
        return bool(self._inspect()["visible"])

    def is_enabled(self) -> bool:
        return bool(self._inspect()["enabled"])

    def is_editable(self) -> bool:
        return bool(self._inspect()["editable"])

    def _action(self, op: str, **extra: Any) -> dict[str, Any]:
        return self.page._post("/page/action", {"op": op, **self._target(), **extra})

    def focus(self, *, timeout: int = 3_000) -> None:
        del timeout
        self._action("focus")

    def fill(self, value: str, *, timeout: int = 3_000) -> None:
        del timeout
        self._action("fill", value=value)

    def press(self, key: str, *, timeout: int = 3_000) -> None:
        del timeout
        self._action("press", key=key)

    def select_option(self, *, label: str, timeout: int = 3_000) -> list[str]:
        del timeout
        return list(self._action("select", value=label).get("selected", []))

    def set_checked(self, checked: bool, *, timeout: int = 3_000) -> None:
        del timeout
        self._action("set_checked", checked=checked)

    def scroll_into_view_if_needed(self, *, timeout: int = 3_000) -> None:
        del timeout
        self._action("scroll")


class RemoteKeyboard:
    def __init__(self, page: RemotePage) -> None:
        self.page = page

    def press(self, key: str) -> None:
        self.page._post("/page/action", {"op": "keyboard_press", "key": key})


class RemotePage:
    """Expose only the semantic Page surface already consumed by agent components."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
            trust_env=False,
            transport=transport,
        )
        self.keyboard = RemoteKeyboard(self)

    def _get(self, path: str) -> dict[str, Any]:
        response = self.client.get(path)
        if not response.is_success:
            raise RemoteBridgeError(f"Browser bridge {response.status_code}: {response.text}")
        return response.json()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(path, json=payload)
        if not response.is_success:
            raise RemoteBridgeError(f"Browser bridge {response.status_code}: {response.text}")
        return response.json()

    @property
    def url(self) -> str:
        return str(self._get("/page/meta")["url"])

    def title(self) -> str:
        return str(self._get("/page/meta")["title"])

    def locator(self, selector: str) -> RemoteLocator:
        if selector not in {"body", ":focus"}:
            raise RemoteBridgeError("Remote locator hanya mendukung body dan :focus.")
        return RemoteLocator(self, selector=selector)

    def get_by_role(self, role: str, *, name: str | None = None, exact: bool = True) -> RemoteLocator:
        return RemoteLocator(self, role=role, name=name, exact=exact)

    def goto(self, value: str, *, wait_until: str, timeout: int) -> None:
        del wait_until, timeout
        self._post("/page/action", {"op": "goto", "value": value})

    def go_back(self, *, wait_until: str, timeout: int) -> object | None:
        del wait_until, timeout
        result = self._post("/page/action", {"op": "go_back"})
        return object() if result.get("moved") else None

    def wait_for_timeout(self, duration_ms: int) -> None:
        self._post("/page/action", {"op": "wait", "duration_ms": duration_ms})

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def close(self) -> None:
        self.client.close()
