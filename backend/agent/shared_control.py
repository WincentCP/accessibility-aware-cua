"""Atomic pause/takeover control, verified focus handoff, and safe resume."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from backend.agent.contracts import ClosedModel, FocusHandoff, HandoffStatus, Observation
from backend.agent.observer import AccessibilityObserver
from backend.agent.resolver import SemanticTargetResolver


def utc_now() -> datetime:
    return datetime.now(UTC)


class ControlBlockReason(StrEnum):
    PAUSED = "PAUSED"
    TAKEOVER_ACTIVE = "TAKEOVER_ACTIVE"


class ActionLease(ClosedModel):
    lease_id: UUID = Field(default_factory=uuid4)
    started_at: datetime = Field(default_factory=utc_now)


class ControlSnapshot(ClosedModel):
    pause_requested: bool
    takeover_active: bool
    active_action_count: int
    checkpoint_safe: bool


class AtomicControlGate:
    """Linearizable gate: pause/takeover and action start share one lock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pause_requested = False
        self._takeover_active = False
        self._active_leases: set[UUID] = set()

    def begin_action(self) -> ActionLease:
        with self._lock:
            if self._takeover_active:
                raise PermissionError(ControlBlockReason.TAKEOVER_ACTIVE.value)
            if self._pause_requested:
                raise PermissionError(ControlBlockReason.PAUSED.value)
            lease = ActionLease()
            self._active_leases.add(lease.lease_id)
            return lease

    def finish_action(self, lease: ActionLease) -> None:
        with self._lock:
            if lease.lease_id not in self._active_leases:
                raise RuntimeError("Action lease tidak aktif atau sudah diselesaikan.")
            self._active_leases.remove(lease.lease_id)

    def request_pause(self) -> ControlSnapshot:
        with self._lock:
            self._pause_requested = True
            return self.snapshot()

    def activate_takeover(self) -> ControlSnapshot:
        with self._lock:
            self._pause_requested = True
            self._takeover_active = True
            return self.snapshot()

    def complete_resync(self) -> ControlSnapshot:
        with self._lock:
            if self._active_leases:
                raise RuntimeError("Resume menunggu action aktif selesai atau timeout.")
            self._takeover_active = False
            self._pause_requested = False
            return self.snapshot()

    def snapshot(self) -> ControlSnapshot:
        with self._lock:
            active = len(self._active_leases)
            return ControlSnapshot(
                pause_requested=self._pause_requested,
                takeover_active=self._takeover_active,
                active_action_count=active,
                checkpoint_safe=self._pause_requested and active == 0,
            )


class FocusHandoffResult(ClosedModel):
    handoff: FocusHandoff
    dom_active_element_verified: bool
    ax_focused_verified: bool
    observation_version: int = Field(ge=1)
    keystrokes: int = Field(ge=0)


class StateDelta(ClosedModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)


class ResumeResult(ClosedModel):
    resumed_at: datetime = Field(default_factory=utc_now)
    before_observation_version: int = Field(ge=1)
    fresh_observation_version: int = Field(ge=1)
    state_delta: StateDelta
    invalidated_semantic_refs: list[str]
    task_map_version: int = Field(ge=1)
    replan_required: bool = True
    active_semantic_ref: None = None
    handoff_status: HandoffStatus = HandoffStatus.COMPLETED


def _signature(node: Any) -> tuple[str, str]:
    return node.role, node.name


def _state_index(observation: Observation) -> dict[tuple[str, str], tuple[Any, ...]]:
    return {
        _signature(node): (
            node.value_summary,
            node.disabled,
            node.selected,
            node.checked,
            node.expanded,
            tuple(sorted(node.states.items())),
        )
        for node in observation.nodes
    }


def semantic_state_delta(before: Observation, after: Observation) -> StateDelta:
    old = _state_index(before)
    new = _state_index(after)
    render = lambda item: f"{item[0]}:{item[1]}"  # noqa: E731
    return StateDelta(
        added=sorted(render(item) for item in new.keys() - old.keys()),
        removed=sorted(render(item) for item in old.keys() - new.keys()),
        changed=sorted(render(item) for item in old.keys() & new.keys() if old[item] != new[item]),
    )


class SharedControlService:
    def __init__(
        self,
        observer: AccessibilityObserver,
        resolver: SemanticTargetResolver,
        gate: AtomicControlGate,
    ) -> None:
        self.observer = observer
        self.resolver = resolver
        self.gate = gate

    def focus_handoff(self, page: Any, *, run_id: UUID, target_ref: str) -> FocusHandoffResult:
        current = self.observer.registry.current
        if current is None:
            raise RuntimeError("Focus handoff memerlukan observation aktif.")
        old_target = next((node for node in current.nodes if node.node_id == target_ref), None)
        if old_target is None:
            raise KeyError("Target handoff tidak ada pada observation aktif.")
        target_signature = _signature(old_target)
        self.gate.activate_takeover()

        fresh = self.observer.capture(page)
        candidates = [node for node in fresh.nodes if _signature(node) == target_signature]
        if len(candidates) != 1:
            raise RuntimeError("Target handoff tidak unik pada fresh observation.")
        resolved = self.resolver.resolve(
            page,
            target_ref=candidates[0].node_id,
            observation_version=fresh.version,
        )
        resolved.locator.focus(timeout=3_000)
        dom_verified = bool(
            resolved.locator.evaluate("element => element === document.activeElement")
        )

        focused_observation = self.observer.capture(page)
        focused_candidates = [
            node for node in focused_observation.nodes if _signature(node) == target_signature
        ]
        ax_verified = len(focused_candidates) == 1 and focused_candidates[0].focused
        focused_ref = focused_candidates[0].node_id if len(focused_candidates) == 1 else None
        announcement = f"Kontrol diserahkan pada {old_target.role} {old_target.name}."
        handoff = FocusHandoff(
            run_id=run_id,
            status=HandoffStatus.ACTIVE,
            target_ref=focused_ref,
            announcement=announcement,
        )
        if not dom_verified or not ax_verified:
            raise RuntimeError("Focus handoff gagal diverifikasi pada DOM atau accessibility tree.")
        return FocusHandoffResult(
            handoff=handoff,
            dom_active_element_verified=dom_verified,
            ax_focused_verified=ax_verified,
            observation_version=focused_observation.version,
            keystrokes=0,
        )

    def resume(self, page: Any, *, task_map_version: int) -> ResumeResult:
        before = self.observer.registry.current
        if before is None:
            raise RuntimeError("Resume memerlukan observation sebelum aksi pengguna.")
        if not self.gate.snapshot().takeover_active:
            raise RuntimeError("Resume hanya valid setelah takeover aktif.")
        fresh = self.observer.capture(page)
        delta = semantic_state_delta(before, fresh)
        result = ResumeResult(
            before_observation_version=before.version,
            fresh_observation_version=fresh.version,
            state_delta=delta,
            invalidated_semantic_refs=[node.node_id for node in before.nodes],
            task_map_version=task_map_version + 1,
        )
        self.gate.complete_resync()
        return result


class ConstraintUpdate(ClosedModel):
    version: int = Field(ge=1)
    user_text: str = Field(min_length=1, max_length=4_000)
    goal_before: str
    goal_after: str
    constraints_after: list[str]
    actor: str = "USER"
    created_at: datetime = Field(default_factory=utc_now)
