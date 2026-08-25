"""Accessibility-tree observer backed by Playwright with a documented CDP fallback."""

from __future__ import annotations

import time
from typing import Any

from packages.agent.contracts import AXNode, Observation
from packages.agent.semantic_snapshot import (
    ACTIONABLE_ROLES,
    DraftAXNode,
    ObserverErrorCode,
    SnapshotRegistry,
    TargetQuery,
    build_observation,
    parse_aria_snapshot,
    prune_nodes,
)


class SemanticResolutionError(RuntimeError):
    def __init__(self, code: ObserverErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code


def _cdp_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value")
    return value


def parse_cdp_ax_tree(payload: dict[str, Any]) -> list[DraftAXNode]:
    """Normalize ``Accessibility.getFullAXTree`` output for fallback use only."""

    raw_nodes = {
        str(item.get("nodeId")): item
        for item in payload.get("nodes", [])
        if not item.get("ignored", False)
    }
    child_ids = {
        str(child_id)
        for item in raw_nodes.values()
        for child_id in item.get("childIds", [])
        if str(child_id) in raw_nodes
    }

    def convert(raw: dict[str, Any]) -> DraftAXNode:
        role = str(_cdp_value(raw.get("role")) or "generic").casefold()
        name = str(_cdp_value(raw.get("name")) or "")
        value = _cdp_value(raw.get("value"))
        states: dict[str, str | bool | int] = {}
        for prop in raw.get("properties", []):
            key = str(prop.get("name", ""))
            prop_value = _cdp_value(prop.get("value"))
            if key and isinstance(prop_value, str | bool | int):
                states[key] = prop_value
        children = [
            convert(raw_nodes[str(child_id)])
            for child_id in raw.get("childIds", [])
            if str(child_id) in raw_nodes
        ]
        return DraftAXNode(
            role=role,
            name=" ".join(name.split()),
            value_summary=None if value is None else " ".join(str(value).split()),
            states=states,
            children=children,
        )

    roots = [raw for node_id, raw in raw_nodes.items() if node_id not in child_ids]
    return [convert(root) for root in roots]


class AccessibilityObserver:
    """Capture, compact, version, and resolve one browser page semantically."""

    def __init__(
        self,
        registry: SnapshotRegistry | None = None,
        *,
        excluded_names: set[str] | None = None,
        allow_cdp_fallback: bool = True,
    ) -> None:
        self.registry = registry or SnapshotRegistry()
        self.excluded_names = excluded_names
        self.allow_cdp_fallback = allow_cdp_fallback

    def _focused_signature(self, page: Any) -> tuple[str, str] | None:
        """Read focus semantically; ``:focus`` is generic and never an action target."""

        focused = page.locator(":focus")
        if focused.count() != 1:
            return None
        try:
            candidates = parse_aria_snapshot(focused.aria_snapshot(timeout=1_000))
        except Exception:
            return None
        stack = list(candidates)
        while stack:
            node = stack.pop(0)
            if node.role in ACTIONABLE_ROLES or node.role in {"heading", "main", "dialog"}:
                return node.role, node.name
            stack[0:0] = node.children
        return None

    def _aria_nodes(self, page: Any, root: Any | None) -> tuple[str, list[DraftAXNode]]:
        semantic_root = root if root is not None else page.locator("body")
        aria_yaml = semantic_root.aria_snapshot(timeout=5_000)
        return aria_yaml, parse_aria_snapshot(aria_yaml)

    def _cdp_nodes(self, page: Any) -> list[DraftAXNode]:
        session = page.context.new_cdp_session(page)
        try:
            return parse_cdp_ax_tree(session.send("Accessibility.getFullAXTree"))
        finally:
            session.detach()

    def capture(self, page: Any, *, root: Any | None = None) -> Observation:
        started = time.perf_counter()
        source = "aria_snapshot"
        try:
            raw_snapshot, nodes = self._aria_nodes(page, root)
            raw_char_count = len(raw_snapshot)
        except Exception:
            if not self.allow_cdp_fallback:
                raise
            source = "cdp_full_ax_tree_fallback"
            nodes = self._cdp_nodes(page)
            raw_char_count = len(str(nodes))
        pruned = prune_nodes(
            nodes,
            excluded_names=self.excluded_names if self.excluded_names is not None else (),
        ) if self.excluded_names is not None else prune_nodes(nodes)
        observation = build_observation(
            nodes=pruned,
            version=self.registry.next_version,
            url=page.url,
            title=page.title(),
            raw_char_count=raw_char_count,
            capture_latency_ms=round((time.perf_counter() - started) * 1_000),
            source=source,
            focused_signature=self._focused_signature(page),
        )
        self.registry.install(observation)
        return observation

    def node_for_ref(self, semantic_ref: str) -> AXNode:
        resolution = self.registry.resolve_ref(semantic_ref)
        if resolution.semantic_ref is None or self.registry.current is None:
            raise SemanticResolutionError(resolution.error_code, resolution.message)
        return next(
            node for node in self.registry.current.nodes if node.node_id == resolution.semantic_ref
        )

    def locator_for(self, page: Any, query: TargetQuery) -> Any:
        """Return a strict semantic locator; execution is intentionally Stage 8 scope."""

        resolution = self.registry.query(query)
        if resolution.semantic_ref is None:
            raise SemanticResolutionError(resolution.error_code, resolution.message)
        node = self.node_for_ref(resolution.semantic_ref)
        locator = page.get_by_role(node.role, name=node.name, exact=True)
        count = locator.count()
        if count != 1:
            code = (
                ObserverErrorCode.AMBIGUOUS_TARGET
                if count > 1
                else ObserverErrorCode.TARGET_NOT_FOUND
            )
            raise SemanticResolutionError(code, f"semantic locator matched {count} elements")
        return locator
