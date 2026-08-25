"""Normalize Playwright ARIA YAML into versioned, compact semantic observations.

The module deliberately contains no DOM selectors, coordinates, benchmark oracle
fields, or test IDs.  A semantic reference is scoped to exactly one observation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from packages.agent.contracts import AXNode, Observation

CONTEXT_CHAR_BUDGET = 12_000
ACTIONABLE_ROLES = {
    "button",
    "checkbox",
    "combobox",
    "link",
    "menuitem",
    "option",
    "radio",
    "searchbox",
    "slider",
    "spinbutton",
    "switch",
    "tab",
    "textbox",
}
ESSENTIAL_ROLES = ACTIONABLE_ROLES | {
    "alert",
    "complementary",
    "dialog",
    "document",
    "form",
    "group",
    "heading",
    "list",
    "listitem",
    "main",
    "navigation",
    "note",
    "paragraph",
    "region",
    "status",
    "strong",
    "text",
}
DEFAULT_EXCLUDED_NAMES = frozenset(
    {
        "Breadcrumb",
        "Kontrol eksperimen",
        "Mini-site benchmark",
        "CUA Benchmark Lokal",
        "Lewati ke konten utama",
    }
)
DEFAULT_EXCLUDED_PREFIXES = (
    "Accessibility-Aware CUA extension",
    "Accessibility-Aware CUA side panel",
)
_ATTRIBUTE_RE = re.compile(r"\[([^\]]+)\]")
_VERSIONED_REF_RE = re.compile(r"^v(?P<version>[1-9]\d*):ax\d{4,}$")


class ObserverErrorCode(StrEnum):
    NONE = "NONE"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"


class ResolutionStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    STALE = "STALE"
    AMBIGUOUS = "AMBIGUOUS"


class TargetQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=128)
    name: str = Field(default="", max_length=1_000)
    states: dict[str, str | bool | int] = Field(default_factory=dict)
    observation_version: int = Field(ge=1)


class TargetResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResolutionStatus
    error_code: ObserverErrorCode = ObserverErrorCode.NONE
    semantic_ref: str | None = None
    matches: list[str] = Field(default_factory=list)
    message: str


@dataclass(slots=True)
class DraftAXNode:
    role: str
    name: str = ""
    value_summary: str | None = None
    states: dict[str, str | bool | int] = field(default_factory=dict)
    children: list[DraftAXNode] = field(default_factory=list)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _parse_scalar(value: str) -> str | bool | int:
    lowered = value.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value.isdigit():
        return int(value)
    return value


def _parse_descriptor(descriptor: str) -> tuple[str, str, dict[str, str | bool | int]]:
    descriptor = _normalize_text(descriptor)
    attributes: dict[str, str | bool | int] = {}
    for attribute in _ATTRIBUTE_RE.findall(descriptor):
        if "=" in attribute:
            key, value = attribute.split("=", 1)
            attributes[key] = _parse_scalar(value)
        else:
            attributes[attribute] = True
    core = _ATTRIBUTE_RE.sub("", descriptor).strip()
    if " \"" in core and core.endswith('"'):
        role, quoted_name = core.split(" ", 1)
        try:
            name = json.loads(quoted_name)
        except json.JSONDecodeError:
            name = quoted_name[1:-1]
    else:
        role, name = core, ""
    return role.casefold(), _normalize_text(str(name)), attributes


def parse_aria_snapshot(aria_yaml: str) -> list[DraftAXNode]:
    """Parse Playwright's documented ARIA YAML without reading the DOM."""

    payload = yaml.safe_load(aria_yaml) or []
    if not isinstance(payload, list):
        payload = [payload]

    def visit(entry: Any) -> list[DraftAXNode]:
        if isinstance(entry, str):
            role, name, states = _parse_descriptor(entry)
            return [DraftAXNode(role=role, name=name, states=states)]
        if not isinstance(entry, dict):
            return []
        output: list[DraftAXNode] = []
        for descriptor, value in entry.items():
            descriptor = str(descriptor)
            if descriptor.startswith("/"):
                continue
            role, name, states = _parse_descriptor(descriptor)
            node = DraftAXNode(role=role, name=name, states=states)
            if isinstance(value, list):
                for child in value:
                    if isinstance(child, dict) and len(child) == 1:
                        metadata_key = str(next(iter(child)))
                        if metadata_key.startswith("/"):
                            node.value_summary = _normalize_text(str(child[metadata_key]))
                            continue
                    node.children.extend(visit(child))
            elif value is not None:
                scalar = _normalize_text(str(value))
                if not node.name and role in {"paragraph", "status", "alert", "text", "strong"}:
                    node.name = scalar
                else:
                    node.value_summary = scalar
            output.append(node)
        return output

    nodes: list[DraftAXNode] = []
    for item in payload:
        nodes.extend(visit(item))
    return nodes


def _is_excluded(node: DraftAXNode, excluded_names: set[str], prefixes: tuple[str, ...]) -> bool:
    if node.name in excluded_names:
        return True
    return bool(node.name and node.name.startswith(prefixes))


def prune_nodes(
    nodes: Iterable[DraftAXNode],
    *,
    excluded_names: Iterable[str] = DEFAULT_EXCLUDED_NAMES,
    excluded_prefixes: tuple[str, ...] = DEFAULT_EXCLUDED_PREFIXES,
) -> list[DraftAXNode]:
    """Keep planner-relevant semantics while removing benchmark/app chrome."""

    excluded = set(excluded_names)

    def prune(node: DraftAXNode) -> list[DraftAXNode]:
        if _is_excluded(node, excluded, excluded_prefixes):
            return []
        children: list[DraftAXNode] = []
        seen_non_actionable: set[tuple[str, str, str | None, str]] = set()
        for child in node.children:
            for kept in prune(child):
                signature = (
                    kept.role,
                    kept.name,
                    kept.value_summary,
                    json.dumps(kept.states, sort_keys=True),
                )
                if kept.role not in ACTIONABLE_ROLES and signature in seen_non_actionable:
                    continue
                if kept.role not in ACTIONABLE_ROLES:
                    seen_non_actionable.add(signature)
                children.append(kept)
        node.children = children
        if node.role in ESSENTIAL_ROLES:
            return [node]
        return children

    result: list[DraftAXNode] = []
    for candidate in nodes:
        result.extend(prune(candidate))
    return result


def _draft_payload(nodes: Iterable[DraftAXNode]) -> list[dict[str, Any]]:
    return [
        {
            "role": node.role,
            "name": node.name,
            "value": node.value_summary,
            "states": dict(sorted(node.states.items())),
            "children": _draft_payload(node.children),
        }
        for node in nodes
    ]


def _state_boolean(states: dict[str, Any], key: str) -> bool | None:
    value = states.get(key)
    return value if isinstance(value, bool) else None


def build_observation(
    *,
    nodes: list[DraftAXNode],
    version: int,
    url: str,
    title: str,
    raw_char_count: int,
    capture_latency_ms: int,
    source: str = "aria_snapshot",
    focused_signature: tuple[str, str] | None = None,
) -> Observation:
    """Assign observation-scoped refs and construct the shared contract."""

    canonical = json.dumps(_draft_payload(nodes), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    flattened: list[AXNode] = []
    focused_ref: str | None = None
    counter = 0

    def convert(draft: DraftAXNode) -> str:
        nonlocal counter, focused_ref
        counter += 1
        node_ref = f"v{version}:ax{counter:04d}"
        child_refs = [convert(child) for child in draft.children]
        focused = focused_signature == (draft.role, draft.name) and focused_ref is None
        states = dict(draft.states)
        if focused:
            states["focused"] = True
            focused_ref = node_ref
        level = states.get("level") if isinstance(states.get("level"), int) else None
        node = AXNode(
            node_id=node_ref,
            role=draft.role,
            name=draft.name,
            value_summary=draft.value_summary,
            states=states,
            level=level,
            disabled=bool(states.get("disabled", False)),
            focused=focused,
            selected=_state_boolean(states, "selected"),
            checked=states.get("checked") if "checked" in states else None,
            expanded=_state_boolean(states, "expanded"),
            children=child_refs,
        )
        flattened.append(node)
        return node_ref

    for root in nodes:
        convert(root)
    flattened.sort(key=lambda item: int(item.node_id.rsplit("ax", 1)[1]))
    provisional = Observation(
        version=version,
        url=url,
        title=title,
        nodes=flattened,
        focused_node_id=focused_ref,
        content_hash=content_hash,
        source=source,
        raw_char_count=raw_char_count,
        capture_latency_ms=max(0, capture_latency_ms),
    )
    compact = render_compact(provisional)
    return provisional.model_copy(
        update={
            "compact_char_count": len(compact),
            "estimated_tokens": math.ceil(len(compact) / 4),
        }
    )


def render_compact(observation: Observation) -> str:
    """Render a deterministic planner-facing form with no pixel coordinates."""

    by_id = {node.node_id: node for node in observation.nodes}
    child_ids = {child for node in observation.nodes for child in node.children}
    roots = [node for node in observation.nodes if node.node_id not in child_ids]
    lines = [
        f'page {json.dumps(observation.title, ensure_ascii=False)} url={json.dumps(observation.url, ensure_ascii=False)}',
        f"observation v{observation.version} hash={observation.content_hash}",
    ]

    def emit(node: AXNode, depth: int) -> None:
        states = dict(node.states)
        if node.focused:
            states["focused"] = True
        state_text = ""
        if states:
            state_text = " " + " ".join(
                f"{key}={json.dumps(value, ensure_ascii=False)}"
                for key, value in sorted(states.items())
            )
        value_text = (
            f" value={json.dumps(node.value_summary, ensure_ascii=False)}"
            if node.value_summary is not None
            else ""
        )
        name_text = f" {json.dumps(node.name, ensure_ascii=False)}" if node.name else ""
        lines.append(f"{'  ' * depth}- [{node.node_id}] {node.role}{name_text}{state_text}{value_text}")
        for child_ref in node.children:
            emit(by_id[child_ref], depth + 1)

    for root in roots:
        emit(root, 0)
    return "\n".join(lines)


class SnapshotRegistry:
    """Own the current observation and reject all stale semantic references."""

    def __init__(self) -> None:
        self._current: Observation | None = None

    @property
    def current(self) -> Observation | None:
        return self._current

    @property
    def next_version(self) -> int:
        return 1 if self._current is None else self._current.version + 1

    def install(self, observation: Observation) -> None:
        if observation.version != self.next_version:
            raise ValueError(f"expected observation version {self.next_version}")
        self._current = observation

    def resolve_ref(self, semantic_ref: str) -> TargetResolution:
        match = _VERSIONED_REF_RE.fullmatch(semantic_ref)
        if self._current is None or match is None or int(match.group("version")) != self._current.version:
            return TargetResolution(
                status=ResolutionStatus.STALE,
                error_code=ObserverErrorCode.STALE_OBSERVATION,
                message="Semantic reference berasal dari observation lama atau tidak valid.",
            )
        if any(node.node_id == semantic_ref for node in self._current.nodes):
            return TargetResolution(
                status=ResolutionStatus.FOUND,
                semantic_ref=semantic_ref,
                matches=[semantic_ref],
                message="Semantic reference valid pada observation aktif.",
            )
        return TargetResolution(
            status=ResolutionStatus.NOT_FOUND,
            error_code=ObserverErrorCode.TARGET_NOT_FOUND,
            message="Semantic reference tidak ada pada observation aktif.",
        )

    def query(self, query: TargetQuery) -> TargetResolution:
        if self._current is None or query.observation_version != self._current.version:
            return TargetResolution(
                status=ResolutionStatus.STALE,
                error_code=ObserverErrorCode.STALE_OBSERVATION,
                message="Query memakai observation version yang bukan versi aktif.",
            )
        expected_name = _normalize_text(query.name).casefold()
        matches = []
        for node in self._current.nodes:
            if node.role.casefold() != query.role.casefold():
                continue
            if expected_name and _normalize_text(node.name).casefold() != expected_name:
                continue
            if any(node.states.get(key) != value for key, value in query.states.items()):
                continue
            matches.append(node.node_id)
        if not matches:
            return TargetResolution(
                status=ResolutionStatus.NOT_FOUND,
                error_code=ObserverErrorCode.TARGET_NOT_FOUND,
                message="Tidak ada role, accessible name, dan state yang cocok.",
            )
        if len(matches) > 1:
            return TargetResolution(
                status=ResolutionStatus.AMBIGUOUS,
                error_code=ObserverErrorCode.AMBIGUOUS_TARGET,
                matches=matches,
                message="Lebih dari satu target semantik cocok; konteks tambahan diperlukan.",
            )
        return TargetResolution(
            status=ResolutionStatus.FOUND,
            semantic_ref=matches[0],
            matches=matches,
            message="Target semantik unik ditemukan.",
        )


def within_context_budget(observation: Observation, budget: int = CONTEXT_CHAR_BUDGET) -> bool:
    return observation.compact_char_count <= budget
