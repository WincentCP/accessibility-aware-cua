from __future__ import annotations

from packages.agent.observer import parse_cdp_ax_tree
from packages.agent.semantic_snapshot import prune_nodes


def test_documented_cdp_fallback_normalizes_full_ax_tree() -> None:
    payload = {
        "nodes": [
            {
                "nodeId": "1",
                "role": {"value": "RootWebArea"},
                "name": {"value": "Demo"},
                "childIds": ["2"],
            },
            {
                "nodeId": "2",
                "role": {"value": "button"},
                "name": {"value": "Simpan"},
                "properties": [{"name": "disabled", "value": {"value": False}}],
            },
        ]
    }

    normalized = parse_cdp_ax_tree(payload)
    pruned = prune_nodes(normalized)

    assert len(pruned) == 1
    assert pruned[0].role == "button"
    assert pruned[0].name == "Simpan"
    assert pruned[0].states["disabled"] is False
