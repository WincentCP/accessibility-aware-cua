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
            "Cari perjalanan dari Medan ke Bali untuk tanggal 14 Oktober. Pilih keberangkatan "
            "antara jam sembilan sampai setengah dua belas, dengan harga paling tinggi sembilan "
            "ratus ribu rupiah. Berhenti sebelum pemesanan."
        ),
    },
    {
        "task_id": "T05",
        "label": "Memilih variasi produk",
        "instruction": (
            "Pilih Jaket Demo warna Navy, ukuran M, sebanyak dua. Tambahkan ke keranjang dan "
            "berhenti sebelum pembayaran."
        ),
    },
    {
        "task_id": "T07",
        "label": "Memilih jadwal konsultasi",
        "instruction": (
            "Pilih jadwal konsultasi dengan Rina pada hari Selasa, antara jam satu sampai jam "
            "tiga siang. Simpan untuk diperiksa dan jangan konfirmasi janji."
        ),
    },
    {
        "task_id": "T12",
        "label": "Menyimpan profil sebagai draft",
        "instruction": (
            "Pada profil dummy, isi nama tampilan Budi Demo dan bio Pengguna uji aksesibilitas. "
            "Simpan sebagai draft, lalu berhenti sebelum perubahan diterapkan."
        ),
    },
)

CONSENT_KEYS = ("store_name", "photo", "webcam_audio", "screen")
READINESS_KEYS = ("backend", "agent", "microphone", "camera", "screen", "audio")
VOICE_STATES = {
    "IDLE",
    "SPEAKING",
    "LISTENING",
    "PROCESSING",
    "AGENT_WORKING",
    "COMPLETE",
    "ERROR",
}


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
    automatic_mode: bool = False
    voice_state: str = "IDLE"
    readiness: dict[str, bool] = field(
        default_factory=lambda: {key: False for key in READINESS_KEYS}
    )
    utterances: list[dict[str, Any]] = field(default_factory=list)
    feedback: dict[str, str] | None = None
    participant_name: str | None = None
    participant_name_spelling: str | None = None
    participant_class: str | None = None
    participant_age: int | None = None


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

    def create_automatic(self, *, condition_id: str = "C0") -> dict[str, Any]:
        """Create a one-click session whose short participant profile is collected by voice."""

        session_id = str(uuid4())
        session = StudySession(
            study_session_id=session_id,
            participant_code=f"anon-{session_id[:8]}",
            condition_id=condition_id,
            is_minor=False,
            guardian_consent_confirmed=False,
            status="INITIALIZING",
            automatic_mode=True,
        )
        self._event(session, "SESSION_CREATED", mode="AUTOMATIC_HANDS_FREE")
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

    def set_automatic_readiness(
        self, study_session_id: str, checks: dict[str, bool]
    ) -> dict[str, Any]:
        session = self.get(study_session_id)
        if not session.automatic_mode:
            raise RuntimeError("Sesi ini tidak memakai pemeriksaan otomatis.")
        unknown = set(checks) - set(READINESS_KEYS)
        if unknown:
            raise ValueError(f"Jenis pemeriksaan tidak dikenal: {sorted(unknown)}")
        with self._lock:
            session.readiness.update(checks)
            for key, passed in checks.items():
                self._event(session, "READINESS_CHECK", check_key=key, passed=passed)
            if all(session.readiness.values()):
                session.status = "PROFILE"
                self._event(session, "READINESS_COMPLETE")
            else:
                session.status = "INITIALIZING"
        return self.snapshot(study_session_id)

    def set_participant_profile(
        self,
        study_session_id: str,
        *,
        name: str,
        name_spelling: str,
        participant_class: str,
        age: int,
    ) -> dict[str, Any]:
        session = self.get(study_session_id)
        if session.status not in {"PROFILE", "READY"}:
            raise RuntimeError("Profil peserta belum dapat disimpan pada tahap ini.")
        normalized_name = " ".join(name.split()).strip()
        normalized_spelling = " ".join(name_spelling.split()).strip()
        normalized_class = " ".join(participant_class.split()).strip()
        if not normalized_name or not normalized_spelling or not normalized_class:
            raise ValueError("Nama, ejaan nama, dan kelas wajib diisi.")
        if not 5 <= age <= 30:
            raise ValueError("Umur peserta harus antara 5 dan 30 tahun.")
        with self._lock:
            session.participant_name = normalized_name[:80]
            session.participant_name_spelling = normalized_spelling[:120]
            session.participant_class = normalized_class[:40]
            session.participant_age = age
            session.is_minor = age < 18
            session.status = "READY"
            self._event(session, "PARTICIPANT_PROFILE_RECORDED", age=age)
        return self.snapshot(study_session_id)

    def set_recording_state(self, study_session_id: str, state: str) -> dict[str, Any]:
        session = self.get(study_session_id)
        normalized = state.strip().upper()
        allowed = {"NOT_STARTED", "RECORDING", "STOPPING", "SAVED", "FAILED"}
        if normalized not in allowed:
            raise ValueError("Status perekaman tidak dikenal.")
        with self._lock:
            session.recording_state = normalized
            self._event(session, "RECORDING_STATE", state=normalized)
        return self.snapshot(study_session_id)

    def set_voice_state(self, study_session_id: str, state: str) -> dict[str, Any]:
        session = self.get(study_session_id)
        normalized = state.strip().upper()
        if normalized not in VOICE_STATES:
            raise ValueError("Status percakapan tidak dikenal.")
        with self._lock:
            session.voice_state = normalized
            self._event(session, "VOICE_STATE", state=normalized)
        return self.snapshot(study_session_id)

    def add_utterance(self, study_session_id: str, text: str) -> dict[str, Any]:
        session = self.get(study_session_id)
        normalized = " ".join(text.split()).strip()
        if not normalized:
            raise ValueError("Ucapan kosong tidak dapat disimpan.")
        with self._lock:
            utterance = {
                "utterance_id": len(session.utterances) + 1,
                "text": normalized[:2_000],
                "at": _now(),
            }
            session.utterances.append(utterance)
            session.voice_state = "PROCESSING"
            self._event(session, "UTTERANCE_RECEIVED", utterance_id=utterance["utterance_id"])
        return utterance

    def submit_feedback(self, study_session_id: str, text: str) -> dict[str, Any]:
        session = self.get(study_session_id)
        if session.status != "FEEDBACK":
            raise RuntimeError("Sesi belum siap menerima feedback.")
        normalized = " ".join(text.split()).strip()
        if not normalized:
            raise ValueError("Feedback kosong tidak dapat disimpan.")
        with self._lock:
            session.feedback = {"text": normalized[:4_000], "submitted_at": _now()}
            session.status = "CLOSING"
            session.voice_state = "PROCESSING"
            self._event(session, "FEEDBACK_SUBMITTED")
        return self.snapshot(study_session_id)

    def complete_session(self, study_session_id: str) -> dict[str, Any]:
        session = self.get(study_session_id)
        if session.status != "CLOSING" or not session.feedback:
            raise RuntimeError("Feedback harus tersimpan sebelum sesi diselesaikan.")
        with self._lock:
            session.status = "COMPLETED"
            session.voice_state = "COMPLETE"
            self._event(session, "SESSION_COMPLETED")
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
        if session.task_index >= len(CORE_TASKS):
            session.status = "FEEDBACK"
            session.voice_state = "PROCESSING" if session.automatic_mode else "IDLE"
            self._event(session, "TASKS_COMPLETE")
        else:
            session.status = "BETWEEN_TASKS"
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
            "participant_name": session.participant_name,
            "participant_name_spelling": session.participant_name_spelling,
            "participant_class": session.participant_class,
            "participant_age": session.participant_age,
            "condition_id": session.condition_id,
            "is_minor": session.is_minor,
            "guardian_consent_confirmed": session.guardian_consent_confirmed,
            "status": session.status,
            "consent": dict(session.consent),
            "recording_state": session.recording_state,
            "automatic_mode": session.automatic_mode,
            "voice_state": session.voice_state,
            "readiness": dict(session.readiness),
            "utterances": list(session.utterances[-20:]),
            "feedback": dict(session.feedback) if session.feedback else None,
            "readiness_checks": dict(session.readiness_checks),
            "task_index": session.task_index,
            "task_count": len(CORE_TASKS),
            "current_task": dict(current) if current else None,
            "active_benchmark_session_id": session.active_benchmark_session_id,
            "events": list(session.events[-20:]),
            "created_at": session.created_at,
        }

    def export_result(self, study_session_id: str) -> dict[str, Any]:
        session = self.get(study_session_id)
        with self._lock:
            result = self.snapshot(study_session_id)
            result.update(
                {
                    "format_version": "1.0",
                    "utterances": list(session.utterances),
                    "events": list(session.events),
                    "recordings": {
                        "screen_with_camera": "screen.webm",
                        "camera_backup": "user.webm",
                    },
                }
            )
        return result
