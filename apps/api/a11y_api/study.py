"""In-memory orchestration contract for the hands-free user-study prototype."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

CORE_TASKS: tuple[dict[str, str], ...] = (
    {
        "task_id": "T01",
        "label": "Mencari perjalanan",
        "instruction": (
            "Instruksi kegiatan pertama. Kamu ingin mencari perjalanan dari Medan ke Bali "
            "tanggal 14 Oktober. Keberangkatannya antara jam sembilan sampai setengah dua belas "
            "dan harganya paling tinggi sembilan ratus ribu rupiah. Pilih yang sesuai, tetapi "
            "jangan lakukan pemesanan. Silakan gunakan asisten untuk menyelesaikan kegiatan ini."
        ),
    },
    {
        "task_id": "T05",
        "label": "Memilih variasi produk",
        "instruction": (
            "Instruksi kegiatan kedua. Kamu ingin memilih Jaket Demo warna Navy, ukuran M, "
            "sebanyak dua. Tambahkan ke keranjang, tetapi jangan lanjut ke pembayaran. "
            "Silakan gunakan asisten untuk menyelesaikan kegiatan ini."
        ),
    },
    {
        "task_id": "T07",
        "label": "Memilih jadwal konsultasi",
        "instruction": (
            "Instruksi kegiatan ketiga. Kamu ingin memilih jadwal konsultasi layanan dengan "
            "Rina pada hari Selasa antara jam satu sampai jam tiga siang. Simpan untuk "
            "diperiksa, tetapi jangan mengonfirmasi janji. Silakan gunakan asisten untuk "
            "menyelesaikan kegiatan ini."
        ),
    },
    {
        "task_id": "T12",
        "label": "Menyimpan profil sebagai draft",
        "instruction": (
            "Instruksi kegiatan keempat. Ubah profil dummy dengan nama tampilan Budi Demo dan "
            "bio Pengguna uji aksesibilitas. Simpan sebagai draft, lalu berhenti sebelum "
            "perubahan diterapkan. Silakan gunakan asisten untuk menyelesaikan kegiatan ini."
        ),
    },
)

CONSENT_KEYS = ("store_name", "photo", "webcam_audio", "screen")


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class StudySession:
    study_session_id: str
    participant_code: str
    condition_id: str
    is_minor: bool
    guardian_consent_confirmed: bool
    status: str = "CONSENT"
    consent: dict[str, bool | None] = field(
        default_factory=lambda: {key: None for key in CONSENT_KEYS}
    )
    task_index: int = 0
    active_benchmark_session_id: str | None = None
    recording_state: str = "NOT_STARTED"
    readiness_checks: dict[str, bool | None] = field(
        default_factory=lambda: {"audio": None, "screen_reader": None}
    )
    created_at: str = field(default_factory=_now)
    events: list[dict[str, Any]] = field(default_factory=list)


class StudySessionStore:
    """Thread-safe prototype state; production persistence is the next milestone."""

    def __init__(self, case_store: Any) -> None:
        self.case_store = case_store
        self._sessions: dict[str, StudySession] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _event(session: StudySession, kind: str, **detail: Any) -> None:
        session.events.append({"at": _now(), "kind": kind, **detail})

    def create(
        self,
        *,
        participant_code: str,
        condition_id: str,
        is_minor: bool,
        guardian_consent_confirmed: bool,
    ) -> dict[str, Any]:
        code = " ".join(participant_code.split()).strip()
        if not code:
            raise ValueError("Kode peserta wajib diisi.")
        if is_minor and not guardian_consent_confirmed:
            raise ValueError("Persetujuan orang tua atau wali harus dikonfirmasi terlebih dahulu.")
        session = StudySession(
            study_session_id=str(uuid4()),
            participant_code=code,
            condition_id=condition_id,
            is_minor=is_minor,
            guardian_consent_confirmed=guardian_consent_confirmed,
        )
        self._event(session, "SESSION_CREATED")
        with self._lock:
            self._sessions[session.study_session_id] = session
        return self.snapshot(session.study_session_id)

    def get(self, study_session_id: str) -> StudySession:
        with self._lock:
            try:
                return self._sessions[study_session_id]
            except KeyError as exc:
                raise KeyError("Sesi penelitian tidak ditemukan.") from exc

    def set_consent(self, study_session_id: str, key: str, granted: bool) -> dict[str, Any]:
        if key not in CONSENT_KEYS:
            raise ValueError("Jenis persetujuan tidak dikenal.")
        session = self.get(study_session_id)
        with self._lock:
            session.consent[key] = granted
            self._event(session, "CONSENT_RECORDED", consent_key=key, granted=granted)
            if all(value is not None for value in session.consent.values()):
                session.status = "CHECKS"
                self._event(session, "CONSENT_COMPLETE")
        return self.snapshot(study_session_id)

    def set_readiness_check(
        self, study_session_id: str, key: str, passed: bool
    ) -> dict[str, Any]:
        if key not in {"audio", "screen_reader"}:
            raise ValueError("Jenis pemeriksaan tidak dikenal.")
        session = self.get(study_session_id)
        if session.status not in {"CHECKS", "READY"}:
            raise RuntimeError("Selesaikan consent sebelum pemeriksaan perangkat.")
        with self._lock:
            session.readiness_checks[key] = passed
            self._event(session, "READINESS_CHECK", check_key=key, passed=passed)
            if all(value is True for value in session.readiness_checks.values()):
                session.status = "READY"
                self._event(session, "READINESS_COMPLETE")
            elif session.status == "READY":
                session.status = "CHECKS"
        return self.snapshot(study_session_id)

    def start_task(self, study_session_id: str) -> dict[str, Any]:
        session = self.get(study_session_id)
        if session.status not in {"READY", "BETWEEN_TASKS"}:
            raise RuntimeError("Selesaikan consent atau task aktif sebelum memulai kegiatan.")
        if session.task_index >= len(CORE_TASKS):
            raise RuntimeError("Seluruh kegiatan sudah selesai.")
        task = CORE_TASKS[session.task_index]
        seed = 410_000_000 + session.task_index
        reset = self.case_store.reset(task["task_id"], session.condition_id, seed)
        session.active_benchmark_session_id = str(reset["session_id"])
        session.status = "TASK_ACTIVE"
        self._event(session, "TASK_STARTED", task_id=task["task_id"])
        separator = "&" if "?" in str(reset["start_url"]) else "?"
        return {
            **self.snapshot(study_session_id),
            "instruction": task["instruction"],
            "start_url": (
                f"{reset['start_url']}{separator}study_session_id={session.study_session_id}"
            ),
        }

    def complete_task(self, study_session_id: str, outcome: str) -> dict[str, Any]:
        session = self.get(study_session_id)
        if session.status != "TASK_ACTIVE":
            raise RuntimeError("Tidak ada kegiatan aktif untuk diselesaikan.")
        task = CORE_TASKS[session.task_index]
        self._event(session, "TASK_COMPLETED", task_id=task["task_id"], outcome=outcome)
        session.task_index += 1
        session.active_benchmark_session_id = None
        session.status = "FEEDBACK" if session.task_index >= len(CORE_TASKS) else "BETWEEN_TASKS"
        return self.snapshot(study_session_id)

    def log_event(self, study_session_id: str, kind: str, detail: str = "") -> dict[str, Any]:
        session = self.get(study_session_id)
        normalized = kind.strip().upper()
        if normalized not in {
            "TASK_INSTRUCTION_REPEAT",
            "GUIDANCE_EVENT",
            "RESEARCHER_INTERVENTION",
            "USER_PAUSE",
            "USER_CANCEL",
        }:
            raise ValueError("Jenis event penelitian tidak didukung.")
        self._event(session, normalized, detail=" ".join(detail.split()).strip())
        return self.snapshot(study_session_id)

    def snapshot(self, study_session_id: str) -> dict[str, Any]:
        session = self.get(study_session_id)
        current = CORE_TASKS[session.task_index] if session.task_index < len(CORE_TASKS) else None
        return {
            "study_session_id": session.study_session_id,
            "participant_code": session.participant_code,
            "condition_id": session.condition_id,
            "is_minor": session.is_minor,
            "guardian_consent_confirmed": session.guardian_consent_confirmed,
            "status": session.status,
            "consent": dict(session.consent),
            "recording_state": session.recording_state,
            "readiness_checks": dict(session.readiness_checks),
            "task_index": session.task_index,
            "task_count": len(CORE_TASKS),
            "current_task": dict(current) if current else None,
            "active_benchmark_session_id": session.active_benchmark_session_id,
            "events": list(session.events[-20:]),
            "created_at": session.created_at,
        }
