"""Resolve observation-scoped semantic references to fresh Playwright locators."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from packages.agent.contracts import AXNode, ErrorCode, Observation
from packages.agent.semantic_snapshot import (
    SnapshotRegistry,
    parse_aria_snapshot,
    prune_nodes,
    semantic_content_hash,
)


class ResolverError(RuntimeError):
    """Stable failure raised before a browser action can run."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ResolvedLocator:
    locator: Any
    node: AXNode
    observation_version: int
    semantic_ref: str
    summary: str


class SemanticTargetResolver:
    """Rebuild current locators from role/name; never cache DOM handles/selectors."""

    def __init__(self, registry: SnapshotRegistry) -> None:
        self.registry = registry

    def _active_observation(self, observation_version: int) -> Observation:
        current = self.registry.current
        if current is None or current.version != observation_version:
            raise ResolverError(
                ErrorCode.STALE_OBSERVATION,
                "Action memakai observation version yang bukan versi aktif.",
            )
        return current

    def assert_fresh(self, page: Any, observation_version: int) -> Observation:
        """Reject a DOM re-render/navigation until the caller captures a new observation."""

        current = self._active_observation(observation_version)
        try:
            aria_yaml = page.locator("body").aria_snapshot(timeout=2_000)
        except Exception as exc:
            raise ResolverError(
                ErrorCode.NAVIGATION_INTERRUPTED,
                "Accessibility tree tidak dapat dibaca saat freshness check.",
            ) from exc
        current_hash = semantic_content_hash(prune_nodes(parse_aria_snapshot(aria_yaml)))
        if current_hash != current.content_hash:
            raise ResolverError(
                ErrorCode.STALE_OBSERVATION,
                "Accessibility tree berubah; observe ulang sebelum re-resolve.",
            )
        return current

    def resolve(
        self,
        page: Any,
        *,
        target_ref: str,
        observation_version: int,
        required_states: dict[str, str | bool | int] | None = None,
    ) -> ResolvedLocator:
        observation = self.assert_fresh(page, observation_version)
        reference = self.registry.resolve_ref(target_ref)
        if reference.error_code.value != ErrorCode.NONE.value or reference.semantic_ref is None:
            code = (
                ErrorCode.STALE_OBSERVATION
                if reference.error_code.value == ErrorCode.STALE_OBSERVATION.value
                else ErrorCode.TARGET_NOT_FOUND
            )
            raise ResolverError(code, reference.message)
        node = next(
            (candidate for candidate in observation.nodes if candidate.node_id == target_ref),
            None,
        )
        if node is None:
            raise ResolverError(ErrorCode.TARGET_NOT_FOUND, "Target ref tidak ada pada snapshot aktif.")
        expected_states = required_states or {}
        if any(node.states.get(key) != value for key, value in expected_states.items()):
            raise ResolverError(
                ErrorCode.TARGET_NOT_FOUND,
                "Target ditemukan tetapi state semantiknya tidak cocok.",
            )

        options = {"exact": True}
        if node.name:
            options["name"] = node.name
        locator = page.get_by_role(node.role, **options)
        try:
            count = locator.count()
        except Exception as exc:
            raise ResolverError(
                ErrorCode.NAVIGATION_INTERRUPTED,
                "Browser berubah ketika locator semantik di-resolve.",
            ) from exc
        if count == 0:
            raise ResolverError(
                ErrorCode.TARGET_NOT_FOUND,
                f"Tidak ada locator current untuk role={node.role!r}, name={node.name!r}.",
            )
        if count > 1:
            raise ResolverError(
                ErrorCode.AMBIGUOUS_TARGET,
                f"Locator role/name cocok ke {count} elemen; konteks tambahan wajib.",
            )
        states = json.dumps(node.states, ensure_ascii=False, sort_keys=True)
        summary = f"role={node.role} name={json.dumps(node.name, ensure_ascii=False)} states={states}"
        return ResolvedLocator(
            locator=locator,
            node=node,
            observation_version=observation.version,
            semantic_ref=target_ref,
            summary=summary,
        )
