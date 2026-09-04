from __future__ import annotations

import json
from pathlib import Path

from backend.agent.semantic_snapshot import (
    ObserverErrorCode,
    ResolutionStatus,
    SnapshotRegistry,
    TargetQuery,
    build_observation,
    parse_aria_snapshot,
    prune_nodes,
    render_compact,
    within_context_budget,
)

SAMPLE_ARIA = """
- banner:
  - link "CUA Benchmark Lokal":
    - /url: /
- main:
  - heading "Review perjalanan" [level=1]
  - status: Data siap.
  - textbox "Nama penumpang" [invalid]: Budi
  - checkbox "Setuju" [checked]
  - button "Lanjut"
"""
ROOT = Path(__file__).resolve().parents[1]


def observation_for(registry: SnapshotRegistry, aria: str = SAMPLE_ARIA):
    nodes = prune_nodes(parse_aria_snapshot(aria))
    observation = build_observation(
        nodes=nodes,
        version=registry.next_version,
        url="http://127.0.0.1/review",
        title="Review",
        raw_char_count=len(aria),
        capture_latency_ms=2,
        focused_signature=("textbox", "Nama penumpang"),
    )
    registry.install(observation)
    return observation


def test_aria_parser_normalizes_role_name_value_states_and_focus() -> None:
    registry = SnapshotRegistry()
    observation = observation_for(registry)
    by_name = {node.name: node for node in observation.nodes if node.name}

    assert by_name["Review perjalanan"].role == "heading"
    assert by_name["Review perjalanan"].level == 1
    assert by_name["Nama penumpang"].value_summary == "Budi"
    assert by_name["Nama penumpang"].states["invalid"] is True
    assert by_name["Nama penumpang"].focused is True
    assert by_name["Setuju"].checked is True
    assert observation.focused_node_id == by_name["Nama penumpang"].node_id
    assert all(node.name != "CUA Benchmark Lokal" for node in observation.nodes)


def test_compact_snapshot_has_semantic_refs_but_no_coordinates_or_test_ids() -> None:
    observation = observation_for(SnapshotRegistry())
    compact = render_compact(observation)

    assert "[v1:ax" in compact
    assert 'button "Lanjut"' in compact
    assert "x=" not in compact
    assert "y=" not in compact
    assert "data-testid" not in compact
    assert within_context_budget(observation)


def test_duplicate_accessible_name_is_an_explicit_ambiguity() -> None:
    registry = SnapshotRegistry()
    aria = '- main:\n  - button "Lanjut"\n  - button "Lanjut"\n'
    observation = observation_for(registry, aria)
    result = registry.query(
        TargetQuery(role="button", name="Lanjut", observation_version=observation.version)
    )

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.error_code is ObserverErrorCode.AMBIGUOUS_TARGET
    assert len(result.matches) == 2


def test_new_observation_invalidates_old_semantic_refs_and_queries() -> None:
    registry = SnapshotRegistry()
    first = observation_for(registry)
    old_ref = next(node.node_id for node in first.nodes if node.role == "button")
    second = observation_for(registry, '- main:\n  - button "Selesai"\n')

    stale_ref = registry.resolve_ref(old_ref)
    stale_query = registry.query(
        TargetQuery(role="button", name="Lanjut", observation_version=first.version)
    )
    fresh = registry.query(
        TargetQuery(role="button", name="Selesai", observation_version=second.version)
    )

    assert stale_ref.error_code is ObserverErrorCode.STALE_OBSERVATION
    assert stale_query.status is ResolutionStatus.STALE
    assert fresh.status is ResolutionStatus.FOUND


def test_pruning_preserves_planner_information_and_actionable_duplicates() -> None:
    aria = """
- banner:
  - navigation "Mini-site benchmark":
    - link "Travel"
- main:
  - heading "Form profil" [level=1]
  - paragraph: Isi data dummy saja.
  - alert: Nama wajib diisi.
  - dialog "Konfirmasi perubahan":
    - button "Batal"
    - button "Lanjut"
  - button "Lanjut"
- contentinfo:
  - paragraph: Lingkungan riset lokal.
"""
    pruned = prune_nodes(parse_aria_snapshot(aria))
    observation = build_observation(
        nodes=pruned,
        version=1,
        url="http://127.0.0.1/profile",
        title="Profil",
        raw_char_count=len(aria),
        capture_latency_ms=1,
    )
    roles = {node.role for node in observation.nodes}
    lanjut = [node for node in observation.nodes if node.name == "Lanjut"]

    assert {"heading", "paragraph", "alert", "dialog", "button"} <= roles
    assert len(lanjut) == 2
    assert all(node.name != "Mini-site benchmark" for node in observation.nodes)


def test_public_inventory_covers_36_cases_without_oracle_or_selector_fields() -> None:
    payload = json.loads(
        (ROOT / "benchmark" / "public" / "observer_targets.json").read_text(
            encoding="utf-8"
        )
    )

    def keys(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from keys(nested)

    forbidden = {"oracle", "expected_record_id", "data-testid", "css_selector", "x", "y"}
    assert len(payload["cases"]) == 36
    assert len({case["case_id"] for case in payload["cases"]}) == 36
    assert forbidden.isdisjoint(set(keys(payload["cases"])))
