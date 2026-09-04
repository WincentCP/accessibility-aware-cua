"""Thread-safe, deterministic session state for the Stage 5 mini-sites.

The store keeps the mutable state and oracle-compatible representation on the
server. Public methods return copies with no predicates, expected state, target
annotations, or near-miss fixtures.
"""

from __future__ import annotations

import hashlib
import hmac
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any

from a11y_benchmark.catalog import CONDITIONS, get_task, public_task
from a11y_benchmark.reset.engine import replay_key, reset_case


class SessionNotFound(KeyError):
    """Raised when a benchmark session token is unknown."""


class InvalidAction(ValueError):
    """Raised when submitted task data cannot be applied safely."""


@dataclass(slots=True)
class CaseSession:
    session_id: str
    task_id: str
    condition_id: str
    seed: int
    route: str
    public_fixture: dict[str, Any]
    state: dict[str, Any]
    reset_snapshot_hash: str


def _clean_text(value: Any, *, max_length: int = 120) -> str:
    rendered = str(value or "").strip()
    if len(rendered) > max_length:
        raise InvalidAction(f"Input melebihi {max_length} karakter.")
    return rendered


def _checked(values: dict[str, Any], name: str) -> bool:
    return str(values.get(name, "")).lower() in {"1", "true", "yes", "on"}


class CaseStore:
    def __init__(self, app_secret: str):
        self._secret = app_secret.encode("utf-8")
        self._sessions: dict[str, CaseSession] = {}
        self._lock = RLock()

    def _session_id(self, task_id: str, condition_id: str, seed: int) -> str:
        message = f"stage5|{task_id}|{condition_id}|{seed}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()[:24]

    def reset(self, task_id: str, condition_id: str, seed: int) -> dict[str, Any]:
        task = get_task(task_id)
        if condition_id not in CONDITIONS:
            raise ValueError(f"condition_id tidak dikenal: {condition_id}")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise ValueError("seed harus berupa integer non-negatif.")

        payload = reset_case(task_id, condition_id, seed)
        session_id = self._session_id(task_id, condition_id, seed)
        session = CaseSession(
            session_id=session_id,
            task_id=task_id,
            condition_id=condition_id,
            seed=seed,
            route=task["start_route"],
            public_fixture=deepcopy(payload["public_fixture"]),
            state=deepcopy(payload["state"]),
            reset_snapshot_hash=payload["snapshot_hash"],
        )
        with self._lock:
            self._sessions[session_id] = session
        return self.public_reset_result(session_id)

    def _get(self, session_id: str) -> CaseSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise SessionNotFound(session_id) from exc

    def public_reset_result(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._get(session_id)
            return {
                "session_id": session.session_id,
                "task_id": session.task_id,
                "condition_id": session.condition_id,
                "seed": session.seed,
                "start_url": f"{session.route}?session_id={session.session_id}",
                "snapshot_hash": session.reset_snapshot_hash,
                "replay_key": replay_key(session.task_id, session.condition_id, session.seed),
            }

    def view(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._get(session_id)
            task = get_task(session.task_id)
            return {
                "session_id": session.session_id,
                "task_id": session.task_id,
                "condition_id": session.condition_id,
                "condition": deepcopy(session.public_fixture["condition"]),
                "seed": session.seed,
                "route": session.route,
                "task": public_task(task),
                "records": deepcopy(session.public_fixture["records"]),
                "presentation": deepcopy(session.public_fixture["presentation"]),
                "form": self._public_form_values(session.task_id, session.state),
                "status": self._status(session.task_id, session.state),
            }

    def private_state(self, session_id: str) -> dict[str, Any]:
        """Evaluator-only hook; deliberately absent from every HTTP route."""
        with self._lock:
            return deepcopy(self._get(session_id).state)

    def apply_action(self, session_id: str, values: dict[str, Any]) -> None:
        with self._lock:
            session = self._get(session_id)
            self._apply(session, values)

    def _record_ids(self, session: CaseSession) -> set[str]:
        return {str(item["id"]) for item in session.public_fixture["records"]}

    def _require_record(self, session: CaseSession, value: Any, field: str) -> str:
        record_id = _clean_text(value, max_length=80)
        if record_id not in self._record_ids(session):
            raise InvalidAction(f"{field} tidak tersedia pada fixture aktif.")
        return record_id

    def _apply(self, session: CaseSession, values: dict[str, Any]) -> None:
        task_id = session.task_id
        state = session.state

        if task_id == "T01":
            state["selected_route_id"] = self._require_record(session, values.get("route_id"), "Rute")
            state["phase"] = "review"
        elif task_id == "T02":
            state["filters"]["direct_only"] = _checked(values, "direct_only")
            state["selected_route_id"] = self._require_record(session, values.get("route_id"), "Rute")
            state["phase"] = "review"
        elif task_id == "T03":
            state["passenger"] = {
                "name": _clean_text(values.get("name")),
                "document_id": _clean_text(values.get("document_id"), max_length=40),
            }
            state["accepted_schedule"] = _clean_text(values.get("accepted_schedule"), max_length=20)
            state["phase"] = "review"
        elif task_id == "T04":
            product_id = self._require_record(session, values.get("product_id"), "Produk")
            state["comparison_ids"] = [product_id]
            state["phase"] = "results"
        elif task_id == "T05":
            color = _clean_text(values.get("color"), max_length=30)
            size = _clean_text(values.get("size"), max_length=10)
            try:
                quantity = int(values.get("quantity", 1))
            except (TypeError, ValueError) as exc:
                raise InvalidAction("Jumlah harus berupa angka.") from exc
            if quantity not in {1, 2, 3}:
                raise InvalidAction("Jumlah hanya boleh 1–3 pada benchmark sintetis.")
            matching = [
                record for record in session.public_fixture["records"]
                if record["color"] == color and record["size"] == size
            ]
            sku = matching[0]["id"] if matching else f"invalid-{color.lower()}-{size.lower()}"
            state["selection"] = {"color": color, "size": size, "quantity": quantity}
            state["cart"] = [{"sku": sku, "quantity": quantity}]
            state["phase"] = "cart_ready"
        elif task_id == "T06":
            state["draft"] = {
                "address": _clean_text(values.get("address"), max_length=160),
                "city": _clean_text(values.get("city"), max_length=60),
                "postal_code": _clean_text(values.get("postal_code"), max_length=12),
            }
            state["draft_saved"] = True
            state["phase"] = "draft_saved"
        elif task_id == "T07":
            state["selected_slot_id"] = self._require_record(session, values.get("slot_id"), "Slot")
            state["phase"] = "slot_review"
        elif task_id == "T08":
            state["form"] = {
                "name": _clean_text(values.get("name")),
                "topic": _clean_text(values.get("topic"), max_length=160),
                "date": _clean_text(values.get("date"), max_length=20),
                "time": _clean_text(values.get("time"), max_length=20),
            }
            state["approval_status"] = "pending"
            state["phase"] = "approval_pending"
        elif task_id == "T09":
            state["draft_reschedule"] = {
                "date": _clean_text(values.get("date"), max_length=20),
                "time": _clean_text(values.get("time"), max_length=20),
            }
            state["checkpoint"] = "approval_required"
            state["phase"] = "checkpoint"
        elif task_id == "T10":
            state["notifications"] = {
                "email": _checked(values, "email"),
                "push": _checked(values, "push"),
                "weekly": _checked(values, "weekly"),
            }
            state["saved"] = True
            state["phase"] = "saved"
        elif task_id == "T11":
            state["locale"] = _clean_text(values.get("locale"), max_length=20)
            state["theme"] = _clean_text(values.get("theme"), max_length=20)
            state["saved"] = True
            state["rerender_count"] = 1
            state["phase"] = "saved"
        elif task_id == "T12":
            state["draft_profile"] = {
                "display_name": _clean_text(values.get("display_name")),
                "bio": _clean_text(values.get("bio"), max_length=240),
            }
            state["draft_saved"] = True
            state["approval_status"] = "required"
            state["phase"] = "draft_saved"
        elif task_id == "P01":
            state["selected_route_id"] = self._require_record(
                session, values.get("route_id"), "Rute pilot"
            )
            state["draft_saved"] = True
        elif task_id == "P02":
            selected = []
            if _checked(values, "item_a"):
                selected.append("pmp-a")
            if _checked(values, "item_b"):
                selected.append("pmp-b")
            if not selected:
                raise InvalidAction("Pilih setidaknya satu item pilot.")
            state["comparison_ids"] = selected
        elif task_id == "P03":
            state["selected_slot_id"] = self._require_record(
                session, values.get("slot_id"), "Slot pilot"
            )
        elif task_id == "P04":
            timezone = _clean_text(values.get("timezone"), max_length=40)
            allowed = {str(record["value"]) for record in session.public_fixture["records"]}
            if timezone not in allowed:
                raise InvalidAction("Zona waktu pilot tidak tersedia.")
            state["draft_timezone"] = timezone
            state["draft_saved"] = True
        else:
            raise InvalidAction(f"Task {task_id} belum memiliki handler mini-site.")

    @staticmethod
    def _public_form_values(task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        if task_id in {"T01", "T02"}:
            return {
                "route_id": state.get("selected_route_id"),
                "direct_only": state.get("filters", {}).get("direct_only", False),
            }
        if task_id == "T03":
            return {**state["passenger"], "accepted_schedule": state["accepted_schedule"]}
        if task_id == "T04":
            return {"product_id": (state["comparison_ids"] or [None])[0]}
        if task_id == "T05":
            return deepcopy(state["selection"])
        if task_id == "T06":
            return deepcopy(state["draft"])
        if task_id == "T07":
            return {"slot_id": state["selected_slot_id"]}
        if task_id == "T08":
            return deepcopy(state["form"])
        if task_id == "T09":
            return deepcopy(state["draft_reschedule"] or {"date": "", "time": ""})
        if task_id == "T10":
            return deepcopy(state["notifications"])
        if task_id == "T11":
            return {"locale": state["locale"], "theme": state["theme"]}
        if task_id == "T12":
            return deepcopy(state["draft_profile"] or {"display_name": "", "bio": ""})
        if task_id == "P01":
            return {"route_id": state["selected_route_id"]}
        if task_id == "P02":
            return {
                "item_a": "pmp-a" in state["comparison_ids"],
                "item_b": "pmp-b" in state["comparison_ids"],
            }
        if task_id == "P03":
            return {"slot_id": state["selected_slot_id"]}
        if task_id == "P04":
            return {"timezone": state["draft_timezone"]}
        return {}

    @staticmethod
    def _status(task_id: str, state: dict[str, Any]) -> dict[str, str]:
        phase = state.get("phase", "")
        initial_phases = {"search", "results", "passenger", "product", "address", "slots", "form", "manage", "settings", "appearance", "profile"}
        if phase in initial_phases:
            return {"kind": "ready", "message": "Fixture siap. Belum ada aksi yang dicatat."}
        pilot_ready = {
            "P01": state.get("selected_route_id") is None and not state.get("draft_saved"),
            "P02": not state.get("comparison_ids"),
            "P03": state.get("selected_slot_id") is None,
            "P04": state.get("draft_timezone") is None and not state.get("draft_saved"),
        }
        if pilot_ready.get(task_id):
            return {"kind": "ready", "message": "Fixture pilot siap. Belum ada aksi yang dicatat."}
        messages = {
            "T01": "Rute dipilih. Berhenti di review; booking tidak dilakukan.",
            "T02": "Filter dan rute dicatat. Berhenti di review; booking tidak dilakukan.",
            "T03": "Data penumpang dummy dan jadwal dicatat. Booking tidak dilakukan.",
            "T04": "Pilihan perbandingan disimpan. Cart dan checkout tidak diubah.",
            "T05": "Variasi ditambahkan ke cart sintetis. Checkout tidak dimulai.",
            "T06": "Alamat dummy disimpan sebagai draft. Pesanan tidak dikirim.",
            "T07": "Slot dipilih untuk review. Janji belum dikonfirmasi.",
            "T08": "Form siap dan approval diminta. Janji belum dikonfirmasi.",
            "T09": "Draft reschedule berada di checkpoint approval. Jadwal asli tetap aktif.",
            "T10": "Preferensi notifikasi disimpan.",
            "T11": "Bahasa dan tema disimpan setelah re-render terkontrol.",
            "T12": "Profil dummy disimpan sebagai draft. Profil aktif tidak diubah.",
            "P01": "Rute pilot disimpan sebagai draft. Booking tidak dilakukan.",
            "P02": "Daftar perbandingan pilot diperbarui. Checkout tidak dilakukan.",
            "P03": "Slot pilot dipilih. Appointment belum dikonfirmasi.",
            "P04": "Zona waktu pilot disimpan sebagai draft. Pengaturan aktif tidak berubah.",
        }
        return {"kind": "updated", "message": messages[task_id]}
