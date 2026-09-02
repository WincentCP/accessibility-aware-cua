"""FastAPI entry point for the Stage 4 skeleton and Stage 5 mini-sites."""

from __future__ import annotations

import asyncio
import hmac
import json
from pathlib import Path
from urllib.parse import parse_qs
from uuid import UUID

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from websockets.asyncio.client import connect as websocket_connect

from a11y_benchmark.catalog import CONDITIONS, FINAL_TASKS, PILOT_TASKS
from a11y_benchmark.manifests import final_seed, pilot_seed
from a11y_benchmark.oracles.engine import evaluate
from apps.api.a11y_api import APP_VERSION
from apps.api.a11y_api.config import ROOT, ConfigurationError, Settings
from apps.api.a11y_api.store import CaseStore, InvalidAction, SessionNotFound
from apps.api.a11y_api.study import StudySessionStore
from apps.api.a11y_api.study_report import build_study_report
from packages.agent.gemini_tts import GeminiTTSClient, GeminiTTSQuotaError
from packages.agent.live import LiveAgentManager

PACKAGE_DIR = Path(__file__).resolve().parent
RECORDINGS_DIR = ROOT / ".runtime" / "recordings"
STUDY_RESULTS_DIR = ROOT / ".runtime" / "study-results"
load_dotenv(ROOT / ".env")

TASK_BY_ROUTE = {task["start_route"]: task["id"] for task in [*FINAL_TASKS, *PILOT_TASKS]}
DOMAIN_LABELS = {
    "travel": "Travel Demo",
    "marketplace": "Marketplace Demo",
    "appointment": "Appointment Demo",
    "account": "Account Settings Demo",
}


def _persist_study_result(store: StudySessionStore, study_session_id: str) -> None:
    export = store.export_result(study_session_id)
    STUDY_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target = STUDY_RESULTS_DIR / f"{study_session_id}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(target)


class ResetRequest(BaseModel):
    task_id: str = Field(pattern=r"^(?:T(?:0[1-9]|1[0-2])|P0[1-4])$")
    condition_id: str = Field(pattern=r"^C[0-2]$")
    seed: int = Field(ge=0, le=2_147_483_647)


class LiveRunRequest(BaseModel):
    benchmark_session_id: str = Field(min_length=24, max_length=128)
    goal: str | None = Field(default=None, min_length=1, max_length=4_000)
    configuration: str = Field(default="P", pattern=r"^(?:B1|P)$")


class LiveCommandRequest(BaseModel):
    command: str = Field(pattern=r"^(?:APPROVE|PAUSE|TAKE_OVER|RESUME|CANCEL|REJECT)$")
    transcript: str | None = Field(default=None, max_length=500)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2_000)


class StudySessionRequest(BaseModel):
    participant_code: str = Field(min_length=1, max_length=80)
    condition_id: str = Field(default="C0", pattern=r"^C[0-2]$")
    is_minor: bool = False
    guardian_consent_confirmed: bool = False


class StudyConsentRequest(BaseModel):
    key: str
    granted: bool


class StudyReadinessRequest(BaseModel):
    key: str
    passed: bool


class StudyCompletionRequest(BaseModel):
    outcome: str = Field(min_length=1, max_length=80)


class StudyEventRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    detail: str = Field(default="", max_length=500)


class AutomaticStudyStartRequest(BaseModel):
    condition_id: str = Field(default="C0", pattern=r"^C[0-2]$")


class AutomaticReadinessRequest(BaseModel):
    checks: dict[str, bool]


class ParticipantProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    name_spelling: str = Field(min_length=1, max_length=120)
    participant_class: str = Field(min_length=1, max_length=40)
    age: int = Field(ge=5, le=30)


class StudyStateRequest(BaseModel):
    state: str = Field(min_length=2, max_length=40)


class StudyUtteranceRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2_000)


def _postgres_health(settings: Settings) -> tuple[dict[str, str], bool]:
    if not settings.require_postgres:
        return ({"status": "not_required_for_stage5", "detail": "Aktifkan CUA_REQUIRE_POSTGRES=true untuk gate integrasi."}, True)
    try:
        import psycopg

        with (
            psycopg.connect(settings.database_url, connect_timeout=2) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return ({"status": "ready"}, True)
    except Exception as exc:  # pragma: no cover - depends on external service
        return ({"status": "unavailable", "detail": type(exc).__name__}, False)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    app = FastAPI(
        title="Accessibility-Aware CUA Research API",
        version=APP_VERSION,
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.settings = active_settings
    app.state.case_store = CaseStore(active_settings.app_secret)
    app.state.study_store = StudySessionStore(app.state.case_store)
    app.state.tts_cache = {}
    app.state.live_agent = LiveAgentManager(
        settings=active_settings,
        case_store=app.state.case_store,
    )
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    def render_task(
        request: Request,
        view: dict,
        *,
        status_code: int = 200,
        status_override: dict[str, str] | None = None,
        study_session_id: str | None = None,
    ):
        domain = view["task"]["domain"]
        presentation = view["presentation"]
        if presentation.get("layout_variant") == "reflowed":
            view["records"] = list(reversed(view["records"]))
        if status_override is not None:
            view["status"] = status_override
        return templates.TemplateResponse(
            request=request,
            name="task.html",
            status_code=status_code,
            context={
                **view,
                "domain": domain,
                "domain_label": DOMAIN_LABELS[domain],
                "is_c1": view["condition_id"] == "C1",
                "is_c2": view["condition_id"] == "C2",
                "study_session_id": study_session_id,
                "study_mode": study_session_id is not None,
            },
        )

    @app.get("/health", tags=["health"])
    def health() -> dict:
        return {
            "status": "ok",
            "service": "accessibility-aware-cua-api",
            "version": APP_VERSION,
            "environment": active_settings.environment,
            "planner_provider": active_settings.planner_provider,
        }

    @app.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        database, database_ok = _postgres_health(active_settings)
        payload = {
            "status": "ready" if database_ok else "not_ready",
            "dependencies": {
                "benchmark_catalog": {"status": "ready", "tasks": len(FINAL_TASKS)},
                "database": database,
                "browser_profile": {
                    "status": "configured",
                    "isolated_from_personal_profile": True,
                },
            },
        }
        return JSONResponse(payload, status_code=200 if database_ok else 503)

    @app.post("/api/benchmark/reset", tags=["benchmark"])
    def reset_case_endpoint(payload: ResetRequest) -> dict:
        try:
            return app.state.case_store.reset(payload.task_id, payload.condition_id, payload.seed)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/researcher", response_class=HTMLResponse, include_in_schema=False)
    def researcher_console(request: Request):
        return templates.TemplateResponse(request=request, name="researcher.html", context={})

    @app.get("/api/study/readiness", tags=["study"])
    def automatic_study_readiness() -> dict:
        database, database_ok = _postgres_health(active_settings)
        bridge_ok = False
        try:
            response = httpx.get(
                f"{active_settings.browser_bridge_url}/health",
                headers={"Authorization": f"Bearer {active_settings.app_secret}"},
                timeout=2.0,
                trust_env=False,
            )
            bridge_ok = response.status_code == 200
        except httpx.HTTPError:
            bridge_ok = False
        planner_ok = active_settings.live_agent_enabled and (
            active_settings.planner_provider == "deterministic"
            or bool(active_settings.gemini_api_key)
        )
        return {
            "ready": database_ok and bridge_ok and planner_ok,
            "backend": True,
            "database": database,
            "browser_bridge": {"status": "ready" if bridge_ok else "unavailable"},
            "agent": {"status": "ready" if planner_ok else "unavailable"},
            "tts": {
                "status": "configured"
                if active_settings.tts_enabled and active_settings.gemini_api_key
                else "unavailable"
            },
            "transcription": {
                "status": "configured" if active_settings.gemini_api_key else "unavailable",
                "model": active_settings.stt_model,
            },
        }

    @app.post("/api/study/automatic", tags=["study"], status_code=201)
    def create_automatic_study_session(payload: AutomaticStudyStartRequest) -> dict:
        return app.state.study_store.create_automatic(condition_id=payload.condition_id)

    @app.post("/api/study/sessions/{study_session_id}/automatic-readiness", tags=["study"])
    def record_automatic_readiness(
        study_session_id: str, payload: AutomaticReadinessRequest
    ) -> dict:
        try:
            return app.state.study_store.set_automatic_readiness(
                study_session_id, payload.checks
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/participant-profile", tags=["study"])
    def record_participant_profile(
        study_session_id: str, payload: ParticipantProfileRequest
    ) -> dict:
        try:
            return app.state.study_store.set_participant_profile(
                study_session_id, **payload.model_dump()
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/recording-state", tags=["study"])
    def update_recording_state(study_session_id: str, payload: StudyStateRequest) -> dict:
        try:
            updated = app.state.study_store.set_recording_state(
                study_session_id, payload.state
            )
            if updated["status"] == "COMPLETED":
                _persist_study_result(app.state.study_store, study_session_id)
            return updated
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/voice-state", tags=["study"])
    def update_voice_state(study_session_id: str, payload: StudyStateRequest) -> dict:
        try:
            return app.state.study_store.set_voice_state(study_session_id, payload.state)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/utterances", tags=["study"])
    def add_study_utterance(
        study_session_id: str, payload: StudyUtteranceRequest
    ) -> dict:
        try:
            return app.state.study_store.add_utterance(study_session_id, payload.text)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/feedback", tags=["study"])
    def submit_study_feedback(
        study_session_id: str, payload: StudyUtteranceRequest
    ) -> dict:
        try:
            return app.state.study_store.submit_feedback(study_session_id, payload.text)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/complete", tags=["study"])
    def complete_study_session(study_session_id: str) -> dict:
        try:
            completed = app.state.study_store.complete_session(study_session_id)
            _persist_study_result(app.state.study_store, study_session_id)
            return completed
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/study/sessions/{study_session_id}/recordings/{kind}",
        tags=["study"],
        include_in_schema=False,
    )
    async def append_recording_chunk(
        request: Request,
        study_session_id: str,
        kind: str,
        sequence: int = Query(ge=0),
    ) -> dict:
        if kind not in {"user", "screen"}:
            raise HTTPException(status_code=400, detail="Jenis rekaman tidak dikenal.")
        try:
            app.state.study_store.get(study_session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        chunk = await request.body()
        if not chunk:
            raise HTTPException(status_code=400, detail="Potongan rekaman kosong.")
        if len(chunk) > 32 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Potongan rekaman terlalu besar.")
        session_dir = RECORDINGS_DIR / study_session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        target = session_dir / f"{kind}.webm"
        mode = "wb" if sequence == 0 else "ab"
        with target.open(mode) as output:
            output.write(chunk)
        return {"saved": True, "kind": kind, "sequence": sequence, "bytes": len(chunk)}

    @app.websocket("/api/voice/live-transcription")
    async def live_transcription_proxy(websocket: WebSocket) -> None:
        study_session_id = websocket.query_params.get("study_session_id", "")
        try:
            app.state.study_store.get(study_session_id)
        except KeyError:
            await websocket.close(code=4404, reason="Sesi penelitian tidak ditemukan.")
            return
        if not active_settings.gemini_api_key:
            await websocket.close(code=4503, reason="Gemini belum dikonfigurasi.")
            return

        await websocket.accept()
        upstream_url = (
            "wss://generativelanguage.googleapis.com/ws/"
            "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
            f"?key={active_settings.gemini_api_key}"
        )
        setup = {
            "setup": {
                "model": f"models/{active_settings.stt_model}",
                "generationConfig": {"responseModalities": ["TEXT"]},
                "inputAudioTranscription": {
                    "languageCodes": ["id-ID"],
                    "mode": "SMART",
                    "customVocabulary": [
                        "iya",
                        "sudah",
                        "udah",
                        "lanjut",
                        "ulang",
                        "bacakan pilihan",
                        "Medan",
                        "Bali",
                        "Jaket Demo",
                        "Budi Demo",
                    ],
                },
            }
        }
        try:
            async with websocket_connect(upstream_url, max_size=8 * 1024 * 1024) as upstream:
                await upstream.send(json.dumps(setup))

                async def browser_to_gemini() -> None:
                    while True:
                        message = await websocket.receive_json()
                        audio = message.get("audio")
                        if not isinstance(audio, str) or not audio:
                            continue
                        await upstream.send(
                            json.dumps(
                                {
                                    "realtimeInput": {
                                        "audio": {
                                            "data": audio,
                                            "mimeType": "audio/pcm;rate=16000",
                                        }
                                    }
                                }
                            )
                        )

                async def gemini_to_browser() -> None:
                    async for raw in upstream:
                        payload = json.loads(raw)
                        if payload.get("setupComplete") is not None:
                            await websocket.send_json({"type": "ready"})
                        content = payload.get("serverContent") or {}
                        interim = content.get("interimInputTranscription") or {}
                        final = content.get("inputTranscription") or {}
                        if interim.get("text"):
                            await websocket.send_json(
                                {"type": "interim", "text": interim["text"]}
                            )
                        if final.get("text"):
                            await websocket.send_json(
                                {"type": "final", "text": final["text"]}
                            )

                browser_task = asyncio.create_task(browser_to_gemini())
                gemini_task = asyncio.create_task(gemini_to_browser())
                done, pending = await asyncio.wait(
                    {browser_task, gemini_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    task.result()
        except WebSocketDisconnect:
            return
        except Exception:
            if websocket.client_state.name == "CONNECTED":
                await websocket.send_json(
                    {"type": "error", "message": "Transkripsi langsung terputus."}
                )
                await websocket.close(code=1011)

    @app.post("/api/study/sessions", tags=["study"], status_code=201)
    def create_study_session(payload: StudySessionRequest) -> dict:
        try:
            return app.state.study_store.create(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/study/sessions/{study_session_id}", tags=["study"])
    def get_study_session(study_session_id: str) -> dict:
        try:
            return app.state.study_store.snapshot(study_session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/study/sessions/{study_session_id}/result", tags=["study"])
    def get_study_result(study_session_id: str) -> dict:
        try:
            return app.state.study_store.export_result(study_session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/study/sessions/{study_session_id}/report.pdf",
        tags=["study"],
        response_class=Response,
    )
    def download_study_report(study_session_id: str) -> Response:
        try:
            result = app.state.study_store.export_result(study_session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if result["status"] != "COMPLETED":
            raise HTTPException(status_code=409, detail="Laporan tersedia setelah sesi selesai.")
        report = build_study_report(result)
        filename = f"laporan-penelitian-{result['participant_code']}.pdf"
        return Response(
            report,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/study/sessions/{study_session_id}/consent", tags=["study"])
    def record_study_consent(study_session_id: str, payload: StudyConsentRequest) -> dict:
        try:
            return app.state.study_store.set_consent(study_session_id, payload.key, payload.granted)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/tasks/start", tags=["study"])
    def start_study_task(study_session_id: str) -> dict:
        try:
            return app.state.study_store.start_task(study_session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/checks", tags=["study"])
    def record_study_readiness(
        study_session_id: str, payload: StudyReadinessRequest
    ) -> dict:
        try:
            return app.state.study_store.set_readiness_check(
                study_session_id, payload.key, payload.passed
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/tasks/complete", tags=["study"])
    def complete_study_task(study_session_id: str, payload: StudyCompletionRequest) -> dict:
        try:
            return app.state.study_store.complete_task(study_session_id, payload.outcome)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/events", tags=["study"])
    def log_study_event(study_session_id: str, payload: StudyEventRequest) -> dict:
        try:
            return app.state.study_store.log_event(study_session_id, payload.kind, payload.detail)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/agent/runs", tags=["agent"], status_code=202)
    def start_live_run(payload: LiveRunRequest) -> dict:
        try:
            run = app.state.live_agent.start(
                benchmark_session_id=payload.benchmark_session_id,
                goal=payload.goal,
                configuration=payload.configuration,
            )
            return app.state.live_agent.snapshot(run.run_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sesi benchmark tidak ditemukan.") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/agent/runs/{run_id}", tags=["agent"])
    def get_live_run(run_id: UUID) -> dict:
        try:
            return app.state.live_agent.snapshot(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/agent/runs/{run_id}/commands", tags=["agent"])
    def command_live_run(run_id: UUID, payload: LiveCommandRequest) -> dict:
        try:
            return app.state.live_agent.command(
                run_id, payload.command, transcript=payload.transcript
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/voice/speech", tags=["voice"], response_class=Response)
    def synthesize_speech(payload: SpeechRequest) -> Response:
        if not active_settings.tts_enabled:
            raise HTTPException(status_code=503, detail="Panduan suara AI dinonaktifkan.")
        if active_settings.tts_provider == "gemini":
            if not active_settings.gemini_api_key:
                raise HTTPException(status_code=503, detail="GEMINI_API_KEY belum diisi di .env lokal.")
        else:
            raise HTTPException(status_code=503, detail="TTS hanya mendukung provider Gemini.")
        cache_key = (active_settings.tts_voice, payload.text)
        cached_audio = app.state.tts_cache.get(cache_key)
        if cached_audio is not None:
            return Response(
                content=cached_audio,
                media_type="audio/wav",
                headers={"Cache-Control": "private, max-age=300", "X-TTS-Cache": "HIT"},
            )
        client = GeminiTTSClient(
            active_settings.gemini_api_key,
            model=active_settings.tts_model,
            voice=active_settings.tts_voice,
            max_retries=active_settings.gemini_max_retries,
        )
        try:
            try:
                audio = client.generate(payload.text)
            except GeminiTTSQuotaError:
                if not active_settings.tts_fallback_model:
                    raise
                client.close()
                client = GeminiTTSClient(
                    active_settings.gemini_api_key,
                    model=active_settings.tts_fallback_model,
                    voice=active_settings.tts_voice,
                    max_retries=active_settings.gemini_max_retries,
                )
                audio = client.generate(payload.text)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            client.close()
        if len(app.state.tts_cache) >= 64:
            app.state.tts_cache.pop(next(iter(app.state.tts_cache)))
        app.state.tts_cache[cache_key] = audio
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Cache-Control": "private, max-age=300", "X-TTS-Cache": "MISS"},
        )

    @app.get("/api/benchmark/sessions/{session_id}", tags=["benchmark"])
    def session_view(session_id: str) -> dict:
        try:
            return app.state.case_store.view(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sesi benchmark tidak ditemukan; lakukan reset.") from exc

    @app.get(
        "/internal/evaluation/sessions/{session_id}/oracle",
        include_in_schema=False,
    )
    def evaluator_oracle(request: Request, session_id: str) -> dict:
        """Local evaluator-only boundary; the agent never receives this token or response."""

        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {active_settings.app_secret}"
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="Evaluator tidak terotorisasi.")
        try:
            view = app.state.case_store.view(session_id)
            state = app.state.case_store.private_state(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sesi benchmark tidak ditemukan.") from exc
        return evaluate(view["task_id"], state)

    @app.post("/api/benchmark/sessions/{session_id}/actions", include_in_schema=False)
    async def apply_action(request: Request, session_id: str):
        study_session_id = request.query_params.get("study_session_id")
        try:
            current = app.state.case_store.view(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sesi benchmark tidak ditemukan; lakukan reset.") from exc

        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" not in content_type:
            raise HTTPException(status_code=415, detail="Gunakan form URL-encoded.")
        raw = (await request.body()).decode("utf-8")
        values = {key: entries[-1] for key, entries in parse_qs(raw, keep_blank_values=True).items()}

        delay_ms = int(current["presentation"].get("delay_ms", 0))
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)
        try:
            app.state.case_store.apply_action(session_id, values)
        except InvalidAction as exc:
            refreshed = app.state.case_store.view(session_id)
            return render_task(
                request,
                refreshed,
                status_code=422,
                status_override={
                    "kind": "error",
                    "message": f"Input belum disimpan: {exc}",
                },
                study_session_id=study_session_id,
            )
        study_query = f"&study_session_id={study_session_id}" if study_session_id else ""
        return RedirectResponse(
            f"{current['route']}?session_id={session_id}{study_query}", status_code=303
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home(request: Request):
        domains = [
            {
                "id": domain,
                "label": label,
                "tasks": [
                    {"id": task["id"], "name": task["name"], "route": task["start_route"]}
                    for task in FINAL_TASKS
                    if task["domain"] == domain
                ],
            }
            for domain, label in DOMAIN_LABELS.items()
        ]
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"domains": domains, "version": APP_VERSION},
        )

    @app.get("/{domain}", response_class=HTMLResponse, include_in_schema=False)
    def domain_home(request: Request, domain: str):
        if domain not in DOMAIN_LABELS:
            raise HTTPException(status_code=404, detail="Mini-site tidak ditemukan.")
        tasks = [task for task in FINAL_TASKS if task["domain"] == domain]
        return templates.TemplateResponse(
            request=request,
            name="domain.html",
            context={
                "domain": domain,
                "domain_label": DOMAIN_LABELS[domain],
                "tasks": tasks,
            },
        )

    @app.get("/{domain}/{page_path:path}", response_class=HTMLResponse, include_in_schema=False)
    def task_page(
        request: Request,
        domain: str,
        page_path: str,
        session_id: str | None = Query(default=None),
        task_id: str | None = Query(default=None),
        condition_id: str = Query(default="C0", pattern=r"^C[0-2]$"),
        seed: int | None = Query(default=None, ge=0, le=2_147_483_647),
        study_session_id: str | None = Query(default=None),
    ):
        route = f"/{domain}/{page_path}"
        expected_task_id = TASK_BY_ROUTE.get(route)
        if expected_task_id is None:
            raise HTTPException(status_code=404, detail="Route task tidak ditemukan.")

        if session_id is None:
            selected_task_id = task_id or expected_task_id
            if selected_task_id != expected_task_id:
                raise HTTPException(status_code=400, detail="task_id tidak sesuai dengan route.")
            if condition_id not in CONDITIONS:
                raise HTTPException(status_code=400, detail="condition_id tidak dikenal.")
            selected_seed = seed if seed is not None else (
                pilot_seed(selected_task_id, condition_id)
                if selected_task_id.startswith("P")
                else final_seed(selected_task_id, condition_id, 1)
            )
            reset_result = app.state.case_store.reset(selected_task_id, condition_id, selected_seed)
            return RedirectResponse(reset_result["start_url"], status_code=303)

        try:
            view = app.state.case_store.view(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sesi benchmark tidak ditemukan; lakukan reset.") from exc
        if view["route"] != route:
            raise HTTPException(status_code=400, detail="Sesi tidak cocok dengan route ini.")

        if study_session_id is not None:
            try:
                study = app.state.study_store.snapshot(study_session_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Sesi penelitian tidak ditemukan.") from exc
            if study["active_benchmark_session_id"] != session_id:
                raise HTTPException(status_code=400, detail="Halaman tidak cocok dengan sesi penelitian aktif.")

        return render_task(
            request,
            view,
            study_session_id=study_session_id,
            status_override=(
                {"kind": "ready", "message": "Halaman kegiatan siap."}
                if study_session_id is not None
                and view.get("status", {}).get("message", "").startswith("Fixture siap")
                else None
            ),
        )

    return app


try:
    app = create_app()
except ConfigurationError as configuration_error:
    # Preserve a clear import-time failure for uvicorn/CI instead of silently
    # starting an insecure server with a hard-coded fallback secret.
    raise RuntimeError(f"Konfigurasi API tidak valid: {configuration_error}") from configuration_error


def run() -> None:
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
