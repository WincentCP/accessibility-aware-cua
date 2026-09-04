"""Minimal LangGraph/PostgreSQL checkpoint wiring for durable shared control."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

# Serializer policy must be fixed before the LangGraph checkpoint modules load.
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from backend.agent.state import AgentGraphState


def enforce_safe_serializer() -> None:
    """Use the strict msgpack mode recommended for database-backed checkpoints."""

    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")


@contextmanager
def postgres_checkpointer(database_url: str, *, setup: bool = False) -> Iterator[PostgresSaver]:
    """Open a correctly configured official PostgreSQL saver."""

    enforce_safe_serializer()
    with PostgresSaver.from_conn_string(database_url) as saver:
        if setup:
            saver.setup()
        yield saver


def build_checkpoint_graph(checkpointer: Any):
    """Compile the Stage 6 state-only graph; operational nodes arrive later."""

    builder = StateGraph(AgentGraphState)

    def persist_state(state: AgentGraphState) -> AgentGraphState:
        return state

    builder.add_node("persist_state", persist_state)
    builder.add_edge(START, "persist_state")
    builder.add_edge("persist_state", END)
    return builder.compile(checkpointer=checkpointer)
