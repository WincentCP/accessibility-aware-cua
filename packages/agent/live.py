"""In-process live-run manager connecting FastAPI, LangGraph, and the browser bridge."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from packages.agent.contracts import AgentAction, RelevantItem, VerificationResult
from packages.agent.executor import DeterministicExecutor
from packages.agent.gemini_client import GeminiStructuredClient
from packages.agent.graph import OrchestrationServices, build_agent_graph
from packages.agent.observer import AccessibilityObserver
from packages.agent.openai_client import OpenAIResponsesClient
from packages.agent.planner import PlannerConfig, PlannerDecision, StructuredPlanner
from packages.agent.recovery import RecoveryController
from packages.agent.remote_page import RemotePage
from packages.agent.resolver import SemanticTargetResolver
from packages.agent.task_map import MapControlState, TaskMapCompileInput, TaskMapCompiler
from packages.agent.verifier import PredicateVerifier


@dataclass
class LiveRun:
    run_id: UUID
    agent_session_id: UUID
    benchmark_session_id: str
    task_id: str
    goal: str
    status: str = "QUEUED"
    announcement: str = "Run menunggu browser agent."
    task_map: dict[str, Any] | None = None
    state: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    services: OrchestrationServices | None = None
    cancelled: bool = False


class LiveAgentManager:
    def __init__(self, *, settings: Any, case_store: Any) -> None:
        self.settings = settings
        self.case_store = case_store
        self._runs: dict[UUID, LiveRun] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cua-live-agent")
        self._compiler = TaskMapCompiler()

    def start(self, *, benchmark_session_id: str, goal: str | None = None) -> LiveRun:
        if not self.settings.live_agent_enabled:
            raise RuntimeError("Live agent dinonaktifkan oleh konfigurasi.")
        provider = self.settings.planner_provider
        if provider == "gemini" and not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY belum diisi di .env lokal.")
        if provider == "openai" and not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY belum diisi di .env lokal.")
        if provider not in {"gemini", "openai"}:
            raise RuntimeError(f"Planner provider tidak didukung: {provider}.")
        view = self.case_store.view(benchmark_session_id)
        page = RemotePage(self.settings.browser_bridge_url, self.settings.app_secret)
        try:
            page.health()
        finally:
            page.close()
        benchmark_goal = str(view["task"]["goal"])
        run = LiveRun(
            run_id=uuid4(),
            agent_session_id=uuid4(),
            benchmark_session_id=benchmark_session_id,
            task_id=view["task_id"],
            goal=" ".join((goal or benchmark_goal).split()).strip(),
        )
        if not run.goal:
            raise ValueError("Tujuan tidak boleh kosong.")
        with self._lock:
            self._runs[run.run_id] = run
        self._executor.submit(self._execute, run.run_id)
        return run

    def get(self, run_id: UUID) -> LiveRun:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise KeyError("Live run tidak ditemukan.") from exc

    def snapshot(self, run_id: UUID) -> dict[str, Any]:
        run = self.get(run_id)
        with self._lock:
            return {
                "run_id": str(run.run_id),
                "benchmark_session_id": run.benchmark_session_id,
                "task_id": run.task_id,
                "status": run.status,
                "announcement": run.announcement,
                "task_map": run.task_map,
                "error": run.error,
            }

    def command(self, run_id: UUID, command: str) -> dict[str, Any]:
        run = self.get(run_id)
        normalized = command.upper()
        if normalized in {"CANCEL", "REJECT"}:
            if run.services is not None:
                run.services.control.request_pause()
            run.cancelled = True
            run.status = "CANCELLED"
            run.announcement = "Tugas dibatalkan oleh pengguna."
            return self.snapshot(run_id)
        services = run.services
        if services is None:
            raise RuntimeError("Agent belum siap menerima kontrol.")
        if normalized == "PAUSE":
            services.control.request_pause()
            run.announcement = "Permintaan jeda diterima. Agen berhenti pada checkpoint aman."
        elif normalized == "TAKE_OVER":
            services.control.activate_takeover()
            run.announcement = "Mode ambil alih aktif. Agen tidak menjalankan aksi baru."
        elif normalized == "RESUME":
            if run.status != "WAITING_USER":
                raise RuntimeError("Lanjutkan hanya tersedia setelah agen berhenti di checkpoint aman.")
            services.control.complete_resync()
            run.status = "QUEUED"
            run.announcement = "Agen dilanjutkan dari accessibility tree yang baru."
            self._executor.submit(self._execute, run.run_id)
        else:
            raise ValueError("Command belum didukung pada live bridge.")
        return self.snapshot(run_id)

    def _compile_map(
        self,
        run: LiveRun,
        state: dict[str, Any],
        verifications: list[VerificationResult],
        effects: dict[str, str],
    ) -> None:
        services = run.services
        if services is None or services.observer.registry.current is None:
            return
        observation = services.observer.registry.current
        planned: AgentAction | None = None
        decision_payload = state.get("planner_decision")
        if decision_payload and state.get("route") in {"EXECUTE", "VERIFY"}:
            planned = PlannerDecision.model_validate(decision_payload).action
        relevant = [
            RelevantItem(
                semantic_ref=node.node_id,
                label=f"{node.role}: {node.name}",
                reason="Kontrol semantik pada observasi aktif.",
                observation_version=observation.version,
            )
            for node in observation.nodes
            if node.name and node.role in {"button", "link", "textbox", "combobox", "checkbox", "radio"}
        ][:32]
        control = services.control.snapshot()
        terminal = state.get("terminal_reason")
        summary = None
        if terminal == "COMPLETED":
            summary = "Agen berhenti setelah seluruh langkah yang diklaim selesai lolos verifikasi pasca-aksi."
        elif terminal:
            summary = f"Agen berhenti dengan status {terminal}."
        task_map = self._compiler.compile(
            TaskMapCompileInput(
                session_id=run.agent_session_id,
                run_id=run.run_id,
                version=max(1, int(state.get("task_map_version", 1))),
                goal=run.goal,
                observation=observation,
                verifications=verifications,
                effect_by_step_id=effects,
                planned_action=planned,
                relevant_items=relevant,
                control_state=MapControlState(
                    paused=control.pause_requested,
                    takeover_active=control.takeover_active,
                    approval_pending=bool(state.get("approval_card")),
                    handoff_status=state.get("handoff_status", "NONE"),
                ),
                final_summary=summary,
            )
        )
        run.task_map = task_map.model_dump(mode="json")

    def _execute(self, run_id: UUID) -> None:
        run = self.get(run_id)
        if run.cancelled:
            return
        page = RemotePage(self.settings.browser_bridge_url, self.settings.app_secret)
        model_client: GeminiStructuredClient | OpenAIResponsesClient | None = None
        try:
            observer = AccessibilityObserver(allow_cdp_fallback=False)
            resolver = SemanticTargetResolver(observer.registry)
            if self.settings.planner_provider == "gemini":
                model_client = GeminiStructuredClient(
                    self.settings.gemini_api_key,
                    model=self.settings.planner_model,
                    fallback_model=self.settings.planner_fallback_model,
                    max_retries=self.settings.gemini_max_retries,
                )
                planner_provider = "google-gemini"
            else:
                model_client = OpenAIResponsesClient(
                    self.settings.openai_api_key,
                    model=self.settings.planner_model,
                )
                planner_provider = "openai-responses"
            services = OrchestrationServices(
                page=page,
                observer=observer,
                executor=DeterministicExecutor(resolver),
                verifier=PredicateVerifier(observer),
                planner=StructuredPlanner(
                    model_client,
                    PlannerConfig(model_id=self.settings.planner_model, provider=planner_provider),
                ),
                recovery=RecoveryController(),
            )
            run.services = services
            run.status = "RUNNING"
            run.announcement = "Agen sedang mengamati halaman melalui accessibility tree."
            previous = run.state
            initial = {
                "schema_version": "1.0.0",
                "session_id": str(run.agent_session_id),
                "thread_id": f"live:{run.run_id}",
                "run_id": str(run.run_id),
                "task_id": run.task_id,
                "raw_input": run.goal,
                "step_count": int(previous.get("step_count", 0)),
                "recovery_count": int(previous.get("recovery_count", 0)),
                "replan_count": int(previous.get("replan_count", 0)),
                "task_map_version": int(previous.get("task_map_version", 0)),
                "verified_progress": list(previous.get("verified_progress", [])),
                "planner_telemetry": list(previous.get("planner_telemetry", [])),
                "token_usage": int(previous.get("token_usage", 0)),
                "token_budget": 20_000,
                "max_steps": 12,
                "started_at_ms": int(previous.get("started_at_ms", int(time.time() * 1_000))),
                "handoff_status": "NONE",
                "intervention_count": int(previous.get("intervention_count", 0)),
                "error_code": "NONE",
            }
            graph = build_agent_graph(services)
            verifications: list[VerificationResult] = []
            seen_verifications: set[UUID] = set()
            effects: dict[str, str] = {}
            final_state = initial
            for state in graph.stream(initial, stream_mode="values"):
                final_state = dict(state)
                if run.cancelled:
                    break
                decision_payload = state.get("planner_decision")
                if decision_payload:
                    action = PlannerDecision.model_validate(decision_payload).action
                    effects[str(action.step_id)] = action.expected_effect
                verification_payload = state.get("verification")
                if verification_payload:
                    verification = VerificationResult.model_validate(verification_payload)
                    if verification.verification_id not in seen_verifications:
                        seen_verifications.add(verification.verification_id)
                        verifications.append(verification)
                self._compile_map(run, final_state, verifications, effects)
                run.state = final_state
                run.announcement = self._announcement(final_state)
            if not run.cancelled:
                terminal = final_state.get("terminal_reason")
                run.status = "COMPLETED" if terminal == "COMPLETED" else "WAITING_USER" if final_state.get("pending_interrupt") else "FAILED"
                run.announcement = self._announcement(final_state)
                self._compile_map(run, final_state, verifications, effects)
        except Exception as exc:
            run.status = "FAILED"
            run.error = f"{type(exc).__name__}: {exc}"
            run.announcement = "Live agent gagal dengan aman; tidak ada aksi lanjutan dijalankan."
        finally:
            page.close()
            if model_client is not None:
                model_client.close()

    @staticmethod
    def _announcement(state: dict[str, Any]) -> str:
        if state.get("pending_interrupt"):
            return str(state["pending_interrupt"].get("announcement", "Agen membutuhkan pengguna."))
        if state.get("terminal_reason") == "COMPLETED":
            return "Tugas selesai menurut verifikasi pasca-aksi agent."
        route = state.get("route")
        labels = {
            "EXECUTE": "Tindakan semantik sedang dipersiapkan.",
            "VERIFY": "Tindakan selesai; hasil sedang diverifikasi.",
            "RECOVER": "Verifikasi belum cocok; recovery terbatas dijalankan.",
            "OBSERVE": "Accessibility tree sedang diamati ulang.",
        }
        return labels.get(route, "Agent sedang memproses tujuan.")
